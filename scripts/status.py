"""
Deployment status and drift report.

    python manage.py status
    python manage.py status --chain sonic
    python manage.py status --onchain
    python manage.py status --json out.json --only pending

Answers "what is deployed, and what would change if the deployer ran again" without
deploying anything. Read-only: never sends a transaction, and `manage.py` skips the boa
connection for this command.

Every check is derived from the deployer's own code rather than reimplemented, so the
report cannot drift from what `deploy all` actually does:

  PENDING    Uses fetch_latest_contract() / version_a_gt_version_b() - the same functions
             deploy_contract() uses to decide whether to redeploy. Anything listed here
             gets upgraded automatically on the next run.
  SCHEMA     Walks each YAML against the pydantic models' own `model_fields`. Undeclared
             keys are ignored by pydantic and dropped when the deployer rewrites the file
             through model_dump().
  REQUIRED   Runs DeploymentConfig.model_validate() and reports pydantic's own errors -
             a file that fails here cannot be read or updated by the deployer at all.
  COVERAGE   Chain configs with no deployment, and deployments with no chain config.
  INTEGRITY  Governance roles collapsed onto a single address.
  ONCHAIN    (--onchain) eth_getCode per recorded address, to catch rows that were
             recorded but never actually deployed.

Exits 1 when anything is reported, so it works as a CI gate.
"""

import json
import textwrap
import types
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import NamedTuple, Union, get_args, get_origin

import click
import yaml
from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.markup import escape

from scripts.deploy.models import DeploymentConfig
from scripts.deploy.utils import fetch_latest_contract, get_version_from_filename, version_a_gt_version_b
from scripts.logging_config import get_logger
from settings.config import BASE_DIR

logger = get_logger()

# Explicitly labelled placeholder, not a governance address.
PLACEHOLDER_ADMINS = {"0xabc336d4c71ad275695744d32ddb1d8266db1cbf"}

CHECKS = ("pending", "schema", "required", "coverage", "integrity")

# Colour per check, roughly "how much should this stop you".
KIND_STYLE = {
    "REQUIRED": "red",
    "ONCHAIN": "red",
    "PENDING": "yellow",
    "SCHEMA": "yellow",
    "COVERAGE": "cyan",
    "INTEGRITY": "magenta",
}
KIND_ORDER = ("PENDING", "SCHEMA", "REQUIRED", "COVERAGE", "INTEGRITY", "ONCHAIN")

# Said once per section, so individual rows stay short.
CHECK_BLURB = {
    "PENDING": "the next `deploy all` applies these automatically, no flag needed",
    "SCHEMA": "no model declares these, so model_dump() drops them next time the chain is touched",
    "REQUIRED": "model_validate() raises - the deployer cannot read or update these chains",
    "COVERAGE": "deployments and chain configs that do not line up",
    "INTEGRITY": "governance roles collapsed onto one address",
    "ONCHAIN": "recorded addresses checked against chain state",
}


def plural(count, noun):
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def emit(console, text, indent=0, style="", bullet=""):
    """Print `text` wrapped to the terminal with every continuation line aligned under the
    first. rich.Padding would do the indent but pads each wrapped line out to the block
    width, leaving trailing whitespace in redirected output - so wrap here instead."""
    body_indent = indent + len(bullet)
    width = max(40, console.width - body_indent)
    lines = textwrap.wrap(text, width=width) or [""]
    for number, line in enumerate(lines):
        prefix = " " * indent + (bullet if number == 0 else " " * len(bullet))
        console.print(f"{prefix}[{style}]{escape(line)}[/]" if style else f"{prefix}{escape(line)}")


class Finding(NamedTuple):
    """`items` (chains, slots) is kept separate from prose so the renderer can wrap and
    dim it, and `note` is kept separate so a note shared by a whole section is printed
    once instead of repeated under every row."""

    kind: str
    summary: str
    note: str = ""
    items: tuple = ()  # short tokens (chain names) - rendered space-joined and wrapped
    details: tuple = ()  # full sentences - rendered one per line


# --------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------


def load_deployments(only_chain: str | None = None) -> dict[str, tuple[Path, dict]]:
    """Raw YAML per chain. Deliberately not YamlDeploymentFile.get_deployment_config(),
    which validates - some files fail validation and those are exactly what REQUIRED
    exists to report."""
    out = {}
    for path in sorted((BASE_DIR / "deployments").rglob("*.yaml")):
        if {"debug", "examples"} & set(path.parts):
            continue  # dry-run output and templates, not real deployments
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        chain = (raw.get("config") or {}).get("file_name") or path.stem
        if only_chain and only_chain not in (chain, path.stem):
            continue
        out[chain] = (path, raw)
    return out


def chain_configs() -> dict[str, Path]:
    root = BASE_DIR / "settings" / "chains"
    return {p.stem: p for p in root.rglob("*.yaml") if "examples" not in p.parts}


def contract_rows(raw: dict):
    """Yield (dotted_slot, row) for every contract entry, valid or not."""

    def walk(node, trail):
        if not isinstance(node, dict):
            return
        if "address" in node:
            yield ".".join(trail), node
            return
        for key, value in node.items():
            yield from walk(value, trail + [key])

    yield from walk(raw.get("contracts") or {}, [])


def norm(addr):
    return addr.lower() if isinstance(addr, str) and addr.startswith("0x") else None


# --------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------


def check_pending(deployments):
    """What the next `deploy all` would upgrade, using the deployer's own resolution."""
    grouped, malformed = defaultdict(list), []
    for chain, (_, raw) in deployments.items():
        for slot, row in contract_rows(raw):
            contract_path, recorded = row.get("contract_path"), row.get("contract_version")
            if not contract_path or not recorded:
                continue
            folder = BASE_DIR / Path(str(contract_path).lstrip("/")).parent
            if not folder.is_dir():
                continue
            try:
                latest = fetch_latest_contract(folder)
                available = get_version_from_filename(latest)
            except (FileNotFoundError, ValueError):
                continue
            try:
                newer = version_a_gt_version_b(available, str(recorded))
            except ValueError:
                # version_a_gt_version_b int-casts each dotted part, so a non-numeric
                # recorded version (e.g. the "v3.0.0" style newer contracts declare)
                # breaks the deployer itself on the next run, not just this report.
                malformed.append((chain, slot, recorded))
                continue
            if newer:
                grouped[(slot, str(recorded), available, latest.name)].append(chain)

    findings = [
        Finding(
            "PENDING",
            f"{fname}  {old} -> {new}  ({plural(len(chains), 'chain')})",
            f"slot {slot}",
            tuple(sorted(chains)),
        )
        for (slot, old, new, fname), chains in sorted(grouped.items(), key=lambda kv: -len(kv[1]))
    ]
    for chain, slot, recorded in malformed:
        findings.append(
            Finding(
                "PENDING",
                f"{chain}: {slot} has an unparseable version {recorded!r}",
                "version_a_gt_version_b() raises on this, so the deployer cannot process this chain",
            )
        )
    return findings


def _model_in(annotation):
    """(BaseModel subclass, container) inside an annotation, e.g. `Contract | None` ->
    (Contract, None), `dict[str, Contract] | None` -> (Contract, 'dict')."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin in (Union, types.UnionType):
        for arg in args:
            if arg is not type(None):
                found = _model_in(arg)
                if found[0]:
                    return found
        return None, None
    if origin in (list, set, tuple, frozenset):
        for arg in args:
            found = _model_in(arg)
            if found[0]:
                return found[0], "list"
        return None, None
    if origin is dict and len(args) == 2:
        found = _model_in(args[1])
        if found[0]:
            return found[0], "dict"
        return None, None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation, None
    return None, None


def _undeclared(raw, model: type[BaseModel], trail=()):
    """Keys present in the YAML that `model` does not declare, recursively."""
    if not isinstance(raw, dict):
        return []
    out, fields = [], model.model_fields
    for key, value in raw.items():
        if key not in fields:
            out.append(".".join(trail + (key,)))
            continue
        sub, container = _model_in(fields[key].annotation)
        if sub is None:
            continue
        if container is None:
            out += _undeclared(value, sub, trail + (key,))
        elif container == "dict" and isinstance(value, dict):
            for name, item in value.items():
                out += _undeclared(item, sub, trail + (key, name))
        elif container == "list" and isinstance(value, list):
            for i, item in enumerate(value):
                out += _undeclared(item, sub, trail + (key, f"[{i}]"))
    return out


def check_schema(deployments):
    unknown = defaultdict(set)
    for chain, (_, raw) in deployments.items():
        for key in _undeclared(raw, DeploymentConfig):
            unknown[key].add(chain)
    return [
        Finding("SCHEMA", f"{key}  ({plural(len(chains), 'chain')})", "", tuple(sorted(chains)))
        for key, chains in sorted(unknown.items())
    ]


def _error_row(loc):
    """The contract row an error belongs to, e.g. contracts.amm.stableswap.factory."""
    parts = [str(p) for p in loc]
    parts = parts[: parts.index("compiler_settings")] if "compiler_settings" in parts else parts[:-1]
    return ".".join(parts)


def _describe_error(error):
    """One precise, actionable line for a single pydantic error."""
    where = ".".join(str(p) for p in error["loc"])
    kind, given = error["type"], error.get("input")
    if kind == "missing":
        return f"{where} is missing"
    if kind == "enum":
        expected = (error.get("ctx") or {}).get("expected", "")
        return f"{where} = {given!r} is not valid - expected {expected}"
    if given is None:
        return f"{where} is null but is not optional"
    return f"{where} = {given!r} - {error['msg'][0].lower() + error['msg'][1:]}"


def _summarise_errors(errors, limit=4):
    """Few errors -> spell each one out. Many -> describe the shape, since a file of
    hand-written placeholder rows produces dozens of errors that are really one problem."""
    if len(errors) <= limit:
        return tuple(_describe_error(e) for e in errors)

    rows = {_error_row(e["loc"]) for e in errors}
    fields = sorted({str(e["loc"][-1]) for e in errors})
    # The count is already on the summary line, so lead with the shape instead.
    all_null = all(e.get("input") is None for e in errors)
    lead = (
        f"{plural(len(rows), 'contract row')} with null metadata"
        if all_null
        else f"{plural(len(rows), 'contract row')} affected"
    )
    shown = ", ".join(fields[:6]) + (" ..." if len(fields) > 6 else "")
    return (lead, f"fields: {shown}")


def check_required(deployments):
    """Pydantic's own verdict - these files cannot be loaded by the deployer at all."""
    findings = []
    for chain, (path, raw) in sorted(deployments.items()):
        try:
            DeploymentConfig.model_validate(raw)
        except ValidationError as exc:
            errors = exc.errors()
            findings.append(
                Finding(
                    "REQUIRED",
                    f"{chain}  ({plural(len(errors), 'error')})",
                    path.relative_to(BASE_DIR).as_posix(),
                    (),
                    _summarise_errors(errors),
                )
            )
    return findings


def check_coverage(deployments, configs, selected=None):
    """Repo-wide by nature; `selected` only narrows what is worth printing."""
    findings = []
    for chain, (path, _) in sorted(deployments.items()):
        if selected and chain not in selected:
            continue
        if path.stem not in configs:
            findings.append(
                Finding(
                    "COVERAGE",
                    f"{chain}: deployed, but no settings/chains config",
                    f"{path.relative_to(BASE_DIR).as_posix()} cannot be re-run or updated",
                )
            )
    deployed = {p.stem for p, _ in deployments.values()}
    for stem in sorted(set(configs) - deployed):
        if selected and stem not in selected:
            continue
        findings.append(
            Finding(
                "COVERAGE",
                f"{stem}: chain config exists, never deployed",
                configs[stem].relative_to(BASE_DIR).as_posix(),
            )
        )
    return findings


def check_integrity(deployments):
    by_addr = defaultdict(list)
    for chain, (_, raw) in sorted(deployments.items()):
        dao = (raw.get("config") or {}).get("dao") or {}
        admins = {k: norm(v) for k, v in dao.items() if k.endswith("_admin") and norm(v)}
        if len(admins) > 1 and len(set(admins.values())) == 1:
            by_addr[next(iter(admins.values()))].append(chain)

    findings = []
    for addr, chains in sorted(by_addr.items(), key=lambda kv: -len(kv[1])):
        note = (
            "known placeholder EOA, not a governance address"
            if addr in PLACEHOLDER_ADMINS
            else "zero address" if set(addr[2:]) == {"0"} else "verify this is intended"
        )
        findings.append(
            Finding(
                "INTEGRITY",
                f"{plural(len(chains), 'chain')}: one address holds every admin role",
                f"{addr} - {note}",
                tuple(chains),
            )
        )
    return findings


def check_onchain(deployments, workers=12):
    """Plain JSON-RPC rather than boa: this only needs eth_getCode across many chains,
    and boa binds one network env at a time."""
    jobs = []
    for chain, (_, raw) in deployments.items():
        rpc = (raw.get("config") or {}).get("public_rpc_url")
        if not rpc:
            continue
        for slot, row in contract_rows(raw):
            if norm(row.get("address")):
                jobs.append((chain, slot, norm(row["address"]), rpc))

    def probe(job):
        chain, slot, addr, rpc = job
        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getCode", "params": [addr, "latest"]}).encode()
        request = urllib.request.Request(
            rpc, data=body, headers={"content-type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return chain, slot, addr, json.load(response).get("result")
        except Exception as exc:
            return chain, slot, addr, f"ERR {type(exc).__name__}"

    ghosts, errors, probed = defaultdict(list), Counter(), Counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(probe, job) for job in jobs]):
            chain, slot, addr, code = future.result()
            probed[chain] += 1
            if isinstance(code, str) and code.startswith("ERR"):
                errors[chain] += 1
            elif code in (None, "0x"):
                ghosts[chain].append(f"{slot} {addr}")

    findings = [
        Finding(
            "ONCHAIN",
            f"{chain}: {len(rows)}/{probed[chain]} recorded address(es) have NO bytecode",
            "recorded but never deployed",
            tuple(sorted(rows)),
        )
        for chain, rows in sorted(ghosts.items())
    ]
    # A dead public RPC is infrastructure noise, not a deployment finding.
    findings += [
        Finding(
            "ONCHAIN",
            f"{chain}: unverified, RPC failed on {count}/{probed[chain]} probes",
            "public_rpc_url is dead or rate-limiting - no conclusion drawn",
        )
        for chain, count in sorted(errors.items())
    ]
    return findings


# --------------------------------------------------------------------------------------


@click.command("status", short_help="deployment status and drift report")
@click.option("--chain", metavar="NAME", default=None, help="restrict to one chain")
@click.option("--only", type=click.Choice(CHECKS), default=None, help="run a single check")
@click.option("--onchain", is_flag=True, help="verify every recorded address has bytecode")
@click.option("--json", "json_path", metavar="PATH", default=None, help="write findings as JSON")
def status_command(chain, only, onchain, json_path):
    """Report what is deployed and what the next deploy would change."""
    everything = load_deployments()
    deployments = load_deployments(chain)
    if not deployments:
        # UsageError exits 2, keeping "you invoked this wrong" distinguishable from
        # "drift was found" (1) for CI.
        raise click.UsageError(f"no deployment found for {chain!r}")
    selected = set(deployments) if chain else None
    configs = chain_configs()

    console = Console()
    prod = sum(1 for path, _ in deployments.values() if path.parent.name == "prod")
    scope = (
        f"chain {chain}"
        if chain
        else (f"{len(deployments)} deployments ({prod} prod, {len(deployments) - prod} devnet)")
    )
    console.print(f"[bold]curve-core status[/]  [dim]{scope}, {len(configs)} chain configs[/]\n")

    runners = {
        "pending": lambda: check_pending(deployments),
        "schema": lambda: check_schema(deployments),
        "required": lambda: check_required(deployments),
        "coverage": lambda: check_coverage(everything, configs, selected),
        "integrity": lambda: check_integrity(deployments),
    }
    findings = []
    for name in CHECKS:
        if only in (None, name):
            findings += runners[name]()
    if onchain:
        findings += check_onchain(deployments)

    by_kind = defaultdict(list)
    for finding in findings:
        by_kind[finding.kind].append(finding)

    for kind in KIND_ORDER:
        rows = by_kind.get(kind)
        if not rows:
            continue
        style = KIND_STYLE[kind]
        console.print(f"[bold {style}]{kind}[/] [dim]({len(rows)})[/]")
        emit(console, CHECK_BLURB[kind], indent=2, style="dim italic")

        # A note every row shares is context for the section, not for each row.
        notes = {row.note for row in rows if row.note}
        shared = notes.pop() if len(notes) == 1 and all(row.note for row in rows) else None
        if shared:
            emit(console, shared, indent=2, style="dim italic")

        for row in rows:
            emit(console, row.summary, indent=2, bullet="- ")
            if row.note and not shared:
                emit(console, row.note, indent=6, style="dim")
            for line in row.details:
                emit(console, line, indent=6, style="dim")
            if row.items:
                emit(console, " ".join(row.items), indent=6, style="dim")
        console.print("")

    if json_path:
        Path(json_path).write_text(
            json.dumps([f._asdict() for f in findings], indent=2) + "\n",
            encoding="utf-8",
        )
        # soft_wrap so a long path is never broken across lines (breaks copy/paste).
        console.print(f"[dim]wrote {escape(str(json_path))}[/]", soft_wrap=True)

    if not findings:
        console.print("[bold green]no drift found[/]")
        return

    tally = "  ".join(f"[{KIND_STYLE[k]}]{k} {len(by_kind[k])}[/]" for k in KIND_ORDER if by_kind.get(k))
    console.print(f"[bold]{len(findings)} findings[/]  {tally}")
    raise SystemExit(1)


if __name__ == "__main__":
    status_command()
