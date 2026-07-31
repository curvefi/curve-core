"""
Deployment status and drift report.

    python manage.py status
    python manage.py status --summary
    python manage.py status --chain prod/sonic
    python manage.py status --onchain --wiring --bytecode
    python manage.py status --json out.json --only pending

Answers "what is deployed, and what would change if the deployer ran again" without
deploying anything. Read-only: never sends a transaction, and `manage.py` skips the boa
connection for this command.

Offline checks, run by default. Each is derived from the deployer's own code rather than
reimplemented, so the report cannot drift from what `deploy all` actually does:

  PENDING    Uses fetch_latest_contract() / version_a_gt_version_b() - the same functions
             deploy_contract() uses to decide whether to redeploy. Anything listed here
             gets upgraded automatically on the next run.
  CONFIG     Runs get_chain_settings() over settings/chains. A config it rejects fails
             `deploy all` before it starts, and since the config is copied into the
             deployment file it is usually the root cause of a REQUIRED finding.
  CONTRACTS  Version constants the blueprint path cannot parse, contracts with no version
             constant, and abi/ entries that no longer match a contract path.
  SCHEMA     Walks each YAML against the pydantic models' own `model_fields`. Undeclared
             keys are ignored by pydantic and dropped when the deployer rewrites the file
             through model_dump().
  REQUIRED   Runs DeploymentConfig.model_validate() and reports pydantic's own errors -
             a file that fails here cannot be read or updated by the deployer at all.
  COVERAGE   Chain configs with no deployment, deployments with no chain config, and
             file_name collisions (that field is curve-api-core's blockchain id).
  INTEGRITY  Governance roles collapsed onto a single address.

On-chain checks, each behind its own flag because they need working RPCs:

  ONCHAIN    (--onchain)  eth_getCode per recorded address, to catch rows that were
             recorded but never actually deployed.
  WIRING     (--wiring)   Factory math/views/pool_implementations pointers and contract
             ownership, against what the deployment file records.
  BYTECODE   (--bytecode) Recompiles each contract and compares it to the deployed code.
             The only check that proves contract_path / contract_version / evm_version
             describe what is really on chain. Slow; compilation is cached per source.

Exits 1 when anything is reported, so it works as a CI gate.
"""

import json
import re
import sys
import textwrap
import types
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Union, get_args, get_origin

import click
import vvm
import yaml
from eth_utils import keccak
from pydantic import BaseModel, ValidationError
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from scripts.deploy.models import DeploymentConfig
from scripts.deploy.utils import (
    fetch_latest_contract,
    get_version_from_filename,
    normalise_version,
    version_a_gt_version_b,
)
from scripts.logging_config import get_logger
from settings.config import BASE_DIR, get_chain_settings

logger = get_logger()

# Explicitly labelled placeholder, not a governance address.
PLACEHOLDER_ADMINS = {"0xabc336d4c71ad275695744d32ddb1d8266db1cbf"}

CHECKS = ("pending", "config", "contracts", "schema", "required", "coverage", "integrity")

# Colour per check, roughly "how much should this stop you".
KIND_STYLE = {
    "REQUIRED": "red",
    "CONFIG": "red",
    "ONCHAIN": "red",
    "WIRING": "red",
    "BYTECODE": "red",
    "PENDING": "yellow",
    "CONTRACTS": "yellow",
    "SCHEMA": "yellow",
    "COVERAGE": "cyan",
    "INTEGRITY": "magenta",
}
KIND_ORDER = (
    "PENDING",
    "CONFIG",
    "CONTRACTS",
    "SCHEMA",
    "REQUIRED",
    "COVERAGE",
    "INTEGRITY",
    "ONCHAIN",
    "WIRING",
    "BYTECODE",
)

# Column headers for --summary; short so the matrix stays narrow.
KIND_ABBREV = {
    "PENDING": "pend",
    "CONFIG": "cfg",
    "CONTRACTS": "ctr",
    "SCHEMA": "schema",
    "REQUIRED": "req",
    "COVERAGE": "cov",
    "INTEGRITY": "adm",
    "ONCHAIN": "code",
    "WIRING": "wire",
    "BYTECODE": "src",
}

# Said once per section, so individual rows stay short.
CHECK_BLURB = {
    "PENDING": "the next `deploy all` applies these automatically, no flag needed",
    "CONFIG": "settings/chains inputs that ChainConfig rejects - `deploy all` cannot start on these",
    "CONTRACTS": "contract files the deployer would choke on, or whose ABI has drifted",
    "SCHEMA": "no model declares these, so model_dump() drops them next time the chain is touched",
    "REQUIRED": "model_validate() raises - the deployer cannot read or update these chains",
    "COVERAGE": "deployments and chain configs that do not line up",
    "INTEGRITY": "governance roles collapsed onto one address",
    "ONCHAIN": "recorded addresses checked against chain state",
    "WIRING": "on-chain wiring and ownership vs what the deployment file records",
    "BYTECODE": "recompiled source vs the code actually deployed",
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
    subjects: tuple = ()  # deployment keys this concerns, for the --summary rollup


# --------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------


def load_deployments(only_chain: str | None = None) -> dict[str, tuple[Path, dict]]:
    """Raw YAML per deployment file, keyed "env/stem" (prod/sonic).

    Keyed by path rather than config.file_name because prod and devnet files routinely
    share a file_name - keying on it drops one of every such pair, which is exactly the
    collision COVERAGE reports downstream.

    Deliberately not YamlDeploymentFile.get_deployment_config(), which validates: some
    files fail validation and those are precisely what REQUIRED exists to report.
    """
    out = {}
    for path in sorted((BASE_DIR / "deployments").rglob("*.yaml")):
        if {"debug", "examples"} & set(path.parts):
            continue  # dry-run output and templates, not real deployments
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        key = f"{path.parent.name}/{path.stem}"
        name = (raw.get("config") or {}).get("file_name") or path.stem
        if only_chain and only_chain not in (key, name, path.stem):
            continue
        out[key] = (path, raw)
    return out


def chain_configs() -> dict[str, Path]:
    """Keyed "env/stem" (prod/sonic, devnet/sonic) the way config.file_path is, because a
    chain can legitimately have both a prod and a devnet config - keying on the bare stem
    silently drops one of every such pair."""
    root = BASE_DIR / "settings" / "chains"
    return {f"{p.parent.name}/{p.stem}": p for p in root.rglob("*.yaml") if "examples" not in p.parts}


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

    def scale(chains):
        """prod and devnet counts read very differently - 19 chains sounds alarming until
        you know how many are testnets."""
        prod = sum(1 for c in chains if c.startswith("prod/"))
        if prod and prod < len(chains):
            return f"{plural(len(chains), 'chain')}: {prod} prod, {len(chains) - prod} devnet"
        return f"{plural(len(chains), 'chain')}{'' if prod else ', all devnet'}"

    findings = [
        Finding(
            "PENDING",
            f"{fname}  {old} -> {new}  ({scale(chains)})",
            f"slot {slot}",
            tuple(sorted(chains)),
            subjects=tuple(sorted(chains)),
        )
        for (slot, old, new, fname), chains in sorted(grouped.items(), key=lambda kv: -len(kv[1]))
    ]
    for chain, slot, recorded in malformed:
        findings.append(
            Finding(
                "PENDING",
                f"{chain}: {slot} has an unparseable version {recorded!r}",
                "version_a_gt_version_b() raises on this, so the deployer cannot process this chain",
                subjects=(chain,),
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
        Finding(
            "SCHEMA",
            f"{key}  ({plural(len(chains), 'chain')})",
            "",
            tuple(sorted(chains)),
            subjects=tuple(sorted(chains)),
        )
        for key, chains in sorted(unknown.items())
    ]


def check_config(configs, selected=None):
    """Validate the deploy *inputs*. REQUIRED covers deployment files, but a chain config
    that ChainConfig rejects fails at get_chain_settings() before a deploy even starts -
    and since the config is copied into the deployment file, it is usually the root cause
    of the matching REQUIRED finding."""
    findings = []
    for key, path in sorted(configs.items()):
        if selected and key not in selected:
            continue
        try:
            get_chain_settings(path.relative_to(BASE_DIR / "settings" / "chains").as_posix())
        except ValidationError as exc:
            findings.append(
                Finding(
                    "CONFIG",
                    f"{key}  ({plural(len(exc.errors()), 'error')})",
                    path.relative_to(BASE_DIR).as_posix(),
                    (),
                    _summarise_errors(exc.errors()),
                    subjects=(key,),
                )
            )
        except Exception as exc:  # unreadable yaml, missing file, ...
            findings.append(
                Finding("CONFIG", f"{key}: cannot be loaded", f"{type(exc).__name__}: {exc}", subjects=(key,))
            )
    return findings


# Mirrors the blueprint branch of scripts/deploy/deployment_file.py - a version constant
# that does not match this is a ValueError at deploy time, not a cosmetic problem.
# The optional "v" tracks that regex: upstream declares "v2.1.0", this repo records
# "2.1.0", and the deployer now accepts either.
BLUEPRINT_VERSION_RE = re.compile(r'version:\s*public\(constant\(String\[8\]\)\)\s*=\s*"v?([\d.]+)"')
ANY_VERSION_RE = re.compile(r'version:\s*public\(constant\(String\[8\]\)\)\s*=\s*"([^"]+)"')


def check_contracts():
    """Static problems in contracts/ and abi/ that only surface mid-deploy today."""
    findings = []
    contracts_dir = BASE_DIR / "contracts"

    # Two distinct failures, previously reported as one:
    #  - unparseable: the blueprint regex does not match, so deploy raises immediately;
    #  - mismatched: it parses but disagrees with the _v_NNN filename, so the deploy
    #    succeeds and records a version that contradicts the name fetch_latest_contract
    #    sorts on - silent, and worse for it.
    unparseable, mismatched, no_version = [], [], []
    for source in sorted(contracts_dir.rglob("*_v_*.vy")):
        rel = source.relative_to(BASE_DIR).as_posix()
        digits = re.search(r"_v_(\d+)\.vy$", source.name).group(1)
        implied = ".".join(digits) if len(digits) == 3 else digits
        text = source.read_text(encoding="utf-8")
        declared = ANY_VERSION_RE.search(text)
        if declared is None:
            no_version.append(rel)
        elif not BLUEPRINT_VERSION_RE.search(text):
            unparseable.append(f"{rel}: declares {declared.group(1)!r}")
        elif normalise_version(declared.group(1)) != implied:
            mismatched.append(f"{rel}: declares {declared.group(1)!r}, filename implies {implied!r}")

    if unparseable:
        findings.append(
            Finding(
                "CONTRACTS",
                f"{plural(len(unparseable), 'contract')} with a version the deployer cannot parse",
                "deploying these as a blueprint raises ValueError('Contract version is set "
                "incorrectly'); an optional leading 'v' is accepted, anything else is not",
                (),
                tuple(unparseable),
            )
        )
    if mismatched:
        findings.append(
            Finding(
                "CONTRACTS",
                f"{plural(len(mismatched), 'contract')} with a version contradicting their filename",
                "deploys fine, but records a contract_version that disagrees with the "
                "_v_NNN name fetch_latest_contract orders by",
                (),
                tuple(mismatched),
            )
        )
    if no_version:
        findings.append(
            Finding(
                "CONTRACTS",
                f"{plural(len(no_version), 'contract')} with no version constant",
                "fine for a normal deploy (version() is read on-chain), fatal as a blueprint",
                (),
                tuple(no_version),
            )
        )

    # deploy_contract() writes the ABI to the contract path with contracts->abi swapped,
    # so anything else in abi/ is stale and anything missing will appear on next deploy.
    expected = {f.relative_to(contracts_dir).as_posix().removesuffix(".vy") for f in contracts_dir.rglob("*.vy")}
    present = {
        f.relative_to(BASE_DIR / "abi").as_posix().removesuffix(".json") for f in (BASE_DIR / "abi").rglob("*.json")
    }
    if orphan := sorted(present - expected):
        findings.append(
            Finding(
                "CONTRACTS",
                f"{plural(len(orphan), 'ABI')} no longer match a contract path",
                "the next deploy writes to the new path and leaves these behind",
                (),
                tuple(f"abi/{o}.json" for o in orphan),
            )
        )
    if missing := sorted(expected - present):
        findings.append(
            Finding(
                "CONTRACTS",
                f"{plural(len(missing), 'contract')} have no committed ABI",
                "written on first deploy; absent until then for anyone consuming abi/",
                (),
                tuple(f"contracts/{m}.vy" for m in missing),
            )
        )
    return findings


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


def check_required(deployments, broken_configs=()):
    """Pydantic's own verdict - these files cannot be loaded by the deployer at all.

    `broken_configs` lets a finding point at its cause: the deployer copies the chain
    config into the deployment file, so an invalid config reappears here as an invalid
    deployment. Reporting both without linking them counts one mistake twice.
    """
    findings = []
    for chain, (path, raw) in sorted(deployments.items()):
        try:
            DeploymentConfig.model_validate(raw)
        except ValidationError as exc:
            errors = exc.errors()
            note = path.relative_to(BASE_DIR).as_posix()
            if chain in broken_configs:
                note += "  (inherited from the CONFIG finding above, not a separate mistake)"
            findings.append(
                Finding(
                    "REQUIRED",
                    f"{chain}  ({plural(len(errors), 'error')})",
                    note,
                    (),
                    _summarise_errors(errors),
                    subjects=(chain,),
                )
            )
    return findings


def check_coverage(deployments, configs, selected=None):
    """Repo-wide by nature; `selected` only narrows what is worth printing."""
    findings = []
    # Both sides are keyed env/stem, so a prod deployment needs a prod config and a devnet
    # one a devnet config; matching on the bare name would call a devnet-only chain covered.
    for key, (path, _) in sorted(deployments.items()):
        if selected and key not in selected:
            continue
        if key not in configs:
            findings.append(
                Finding(
                    "COVERAGE",
                    f"{key}: deployed, but no settings/chains config",
                    f"{path.relative_to(BASE_DIR).as_posix()} cannot be re-run or updated",
                    subjects=(key,),
                )
            )
    for key in sorted(set(configs) - set(deployments)):
        if selected and key not in selected:
            continue
        findings.append(
            Finding(
                "COVERAGE",
                f"{key}: chain config exists, never deployed",
                configs[key].relative_to(BASE_DIR).as_posix(),
                subjects=(key,),
            )
        )

    # config.file_name is curve-api-core's blockchain id, and it loads deployments/prod and
    # deployments/devnet into one map - so two files sharing a file_name means one wins and
    # the other is invisible downstream.
    by_name = defaultdict(list)
    for path in sorted((BASE_DIR / "deployments").rglob("*.yaml")):
        if {"debug", "examples"} & set(path.parts):
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        by_name[(raw.get("config") or {}).get("file_name") or path.stem].append(path.relative_to(BASE_DIR).as_posix())
    clashes = {name: paths for name, paths in by_name.items() if len(paths) > 1}
    if clashes and not selected:
        findings.append(
            Finding(
                "COVERAGE",
                f"{plural(len(clashes), 'file_name')} produced by more than one deployment file",
                "file_name is the blockchain id curve-api-core serves, so one shadows the other",
                (),
                tuple(f"{name}: {', '.join(paths)}" for name, paths in sorted(clashes.items())),
                subjects=tuple(f"{Path(p).parent.name}/{Path(p).stem}" for paths in clashes.values() for p in paths),
            )
        )
    return findings


def check_integrity(deployments):
    by_addr = defaultdict(list)
    partial = []
    for chain, (_, raw) in sorted(deployments.items()):
        dao = (raw.get("config") or {}).get("dao") or {}
        admins = {k: norm(v) for k, v in dao.items() if k.endswith("_admin") and norm(v)}
        if len(admins) < 2:
            continue
        if len(set(admins.values())) == 1:
            by_addr[next(iter(admins.values()))].append(chain)
            continue
        # Two of three sharing an address is the same weakness as all three, and used to
        # go unreported because only the fully-collapsed case was checked.
        shared = Counter(admins.values())
        address, count = shared.most_common(1)[0]
        if count > 1:
            roles = sorted(role for role, value in admins.items() if value == address)
            partial.append(f"{chain}: {', '.join(roles)} all = {address}")

    findings = []
    if partial:
        findings.append(
            Finding(
                "INTEGRITY",
                f"{plural(len(partial), 'chain')} share one address across some admin roles",
                "separation is partial - the remaining role(s) differ",
                (),
                tuple(partial),
                subjects=tuple(line.split(":")[0] for line in partial),
            )
        )
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
                subjects=tuple(chains),
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
            subjects=(chain,),
        )
        for chain, rows in sorted(ghosts.items())
    ]
    # A dead public RPC is infrastructure noise, not a deployment finding.
    findings += [
        Finding(
            "ONCHAIN",
            f"{chain}: unverified, RPC failed on {count}/{probed[chain]} probes",
            "public_rpc_url is dead or rate-limiting - no conclusion drawn",
            subjects=(chain,),
        )
        for chain, count in sorted(errors.items())
    ]
    return findings


def _rpc_call(rpc, method, params, timeout=25):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(
        rpc, data=body, headers={"content-type": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response).get("result")


def _eth_call(rpc, to, signature, argument=None):
    data = "0x" + keccak(text=signature).hex()[:8]
    if argument is not None:
        data += f"{argument:064x}"
    return _rpc_call(rpc, "eth_call", [{"to": to, "data": data}, "latest"])


def _as_address(result):
    return "0x" + result[-40:].lower() if isinstance(result, str) and len(result) >= 42 else None


# Deployed code is not the compiler's runtime output verbatim:
#  - normal contracts append immutables and constructor args after the runtime code, so the
#    on-chain code starts with it;
#  - blueprints are deployed via the EIP-5202 wrapper in deployment_utils.deploy_via_create2
#    (b"\x61" + len + b"\x3d\x81\x60\x0a\x3d\x39\xf3" + preamble), 10 bytes that run at
#    creation and are not part of the stored code.
BLUEPRINT_WRAPPER_BYTES = 10


def check_bytecode(deployments, workers=8):
    """Recompile each recorded contract and compare against the code actually on chain.

    This is the only check that proves contract_path / contract_version / evm_version
    describe what was really deployed - everything else trusts the deployment file.
    """
    compiled: dict[tuple, dict] = {}
    missing_compilers = set()

    def compile_row(row):
        settings = row.get("compiler_settings") or {}
        version, evm = settings.get("compiler_version"), settings.get("evm_version")
        source = BASE_DIR / Path(str(row["contract_path"]).lstrip("/"))
        key = (str(source), version, evm)
        if key not in compiled:
            binary = Path.home() / ".vvm" / f"vyper-{version}{'.exe' if sys.platform == 'win32' else ''}"
            if not binary.exists():
                # Falling back to vyper_version= makes vvm query the GitHub release list for
                # every contract, which rate-limits within a few dozen calls. Fail once per
                # version with an actionable message instead.
                missing_compilers.add(version)
                raise FileNotFoundError(
                    f"no local vyper {version}; install it once with "
                    f"`python -c \"import vvm; vvm.install_vyper('{version}')\"`"
                )
            compiled[key] = vvm.compile_source(
                source.read_text(encoding="utf-8"),
                vyper_binary=binary,
                base_path=BASE_DIR,
                evm_version=evm,
            )["<stdin>"]
        return compiled[key]

    jobs = []
    for chain, (_, raw) in deployments.items():
        rpc = (raw.get("config") or {}).get("public_rpc_url")
        if not rpc:
            continue
        for slot, row in contract_rows(raw):
            if row.get("contract_path") and norm(row.get("address")):
                jobs.append((chain, slot, row, rpc))

    # Compile serially (cached, CPU-bound, and vvm shells out) but fetch code concurrently.
    expected = {}
    for chain, slot, row, _ in jobs:
        try:
            output = compile_row(row)
        except Exception as exc:
            expected[(chain, slot)] = ("error", f"{type(exc).__name__}: {exc}")
            continue
        if row.get("deployment_type") == "blueprint":
            code = output.get("blueprint_bytecode", "")[2:]
            expected[(chain, slot)] = ("blueprint", code[BLUEPRINT_WRAPPER_BYTES * 2 :])
        else:
            expected[(chain, slot)] = ("normal", output.get("bytecode_runtime", "")[2:])

    def probe(job):
        chain, slot, row, rpc = job
        try:
            return chain, slot, row, _rpc_call(rpc, "eth_getCode", [norm(row["address"]), "latest"])
        except Exception as exc:
            return chain, slot, row, f"ERR {type(exc).__name__}"

    mismatched, uncompilable, unreachable = defaultdict(list), [], Counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(probe, job) for job in jobs]):
            chain, slot, row, code = future.result()
            kind, want = expected[(chain, slot)]
            if kind == "error":
                uncompilable.append(f"{chain} {slot}: {want}")
                continue
            if not isinstance(code, str) or code.startswith("ERR"):
                unreachable[chain] += 1
                continue
            got = code[2:]
            if not got:
                continue  # no bytecode at all is ONCHAIN's finding, not a mismatch
            ok = got == want if kind == "blueprint" else got.startswith(want)
            if not ok:
                mismatched[chain].append(f"{slot} ({row.get('contract_version')}, {kind})")

    findings = [
        Finding(
            "BYTECODE",
            f"{chain}: {plural(len(slots), 'contract')} do not match their recorded source",
            "recompiling contract_path at contract_version does not reproduce the on-chain code",
            tuple(sorted(slots)),
            subjects=(chain,),
        )
        for chain, slots in sorted(mismatched.items())
    ]
    if missing_compilers:
        findings.append(
            Finding(
                "BYTECODE",
                f"unverified: no local compiler for vyper {', '.join(sorted(missing_compilers))}",
                "install once, then re-run - vvm would otherwise query GitHub per contract "
                "and hit the API rate limit",
                (),
                tuple(f"python -c \"import vvm; vvm.install_vyper('{v}')\"" for v in sorted(missing_compilers)),
            )
        )
    if other := [line for line in uncompilable if "no local vyper" not in line]:
        findings.append(
            Finding(
                "BYTECODE",
                f"{plural(len(other), 'contract')} could not be recompiled to compare",
                "",
                (),
                tuple(sorted(other)[:10]),
            )
        )
    findings += [
        Finding(
            "BYTECODE",
            f"{chain}: unverified, RPC failed on {plural(count, 'probe')}",
            "public_rpc_url is dead or rate-limiting - no conclusion drawn",
            subjects=(chain,),
        )
        for chain, count in sorted(unreachable.items())
    ]
    return findings


# factory getter -> the deployment slot it should point at
FACTORY_WIRING = {
    "math_implementation()": "math",
    "views_implementation()": "views",
}


def check_wiring(deployments, workers=8):
    """The invariants deploy_all establishes: factories pointing at the implementations
    recorded next to them, and ownership handed to the DAO. post_deploy asserts these once
    at deploy time; nothing re-checks them afterwards."""
    findings = []

    def inspect(item):
        chain, raw = item
        rpc = (raw.get("config") or {}).get("public_rpc_url")
        if not rpc:
            return chain, [], [], 0
        wiring, ownership = [], []
        # Count failed calls rather than swallowing them: a dead RPC must report
        # "unverified", never a clean bill of health.
        failures = 0
        amm = ((raw.get("contracts") or {}).get("amm")) or {}
        for group, slots in amm.items():
            if not isinstance(slots, dict) or not (slots.get("factory") or {}).get("address"):
                continue
            factory = norm(slots["factory"]["address"])
            for signature, slot in FACTORY_WIRING.items():
                recorded = norm(((slots.get(slot) or {}).get("address")) or "")
                if not recorded:
                    continue
                try:
                    live = _as_address(_eth_call(rpc, factory, signature))
                except Exception:
                    failures += 1
                    continue
                if live and live != recorded:
                    wiring.append(f"{group}.factory {signature[:-2]} -> {live}, recorded {slot} {recorded}")
            implementation = norm(((slots.get("implementation") or {}).get("address")) or "")
            if implementation:
                try:
                    live = _as_address(_eth_call(rpc, factory, "pool_implementations(uint256)", 0))
                except Exception:
                    live, failures = None, failures + 1
                if live and live != implementation:
                    wiring.append(f"{group}.factory pool_implementations(0) -> {live}, recorded {implementation}")

        owner = norm(((raw.get("config") or {}).get("dao") or {}).get("ownership_admin") or "")
        if owner:
            for slot, row in contract_rows(raw):
                if row.get("deployment_type") == "blueprint" or not norm(row.get("address")):
                    continue
                # admin() first, owner() as fallback; a contract exposing neither is not a
                # finding, but a transport failure on both is counted as unverified.
                answered = False
                for signature in ("admin()", "owner()"):
                    try:
                        live = _as_address(_eth_call(rpc, norm(row["address"]), signature))
                    except Exception:
                        continue
                    answered = True
                    if live is None:
                        continue
                    if live != owner and int(live, 16) != 0:
                        ownership.append(f"{slot} {signature[:-2]}={live}")
                    break
                if not answered:
                    failures += 1
        return chain, wiring, ownership, failures

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(inspect, (chain, raw)) for chain, (_, raw) in deployments.items()]
        for future in as_completed(futures):
            chain, wiring, ownership, failures = future.result()
            if failures:
                findings.append(
                    Finding(
                        "WIRING",
                        f"{chain}: unverified, {plural(failures, 'call')} failed",
                        "public_rpc_url is dead or rate-limiting - no conclusion drawn",
                        subjects=(chain,),
                    )
                )
            if wiring:
                findings.append(
                    Finding(
                        "WIRING",
                        f"{chain}: {plural(len(wiring), 'factory pointer')} out of sync with the deployment file",
                        "",
                        (),
                        tuple(wiring),
                        subjects=(chain,),
                    )
                )
            if ownership:
                findings.append(
                    Finding(
                        "WIRING",
                        f"{chain}: {plural(len(ownership), 'contract')} not owned by ownership_admin",
                        "transfer_ownership runs last in deploy_all and only warns on failure",
                        (),
                        tuple(sorted(ownership)),
                        subjects=(chain,),
                    )
                )
    return sorted(findings, key=lambda f: f.summary)


# --------------------------------------------------------------------------------------


def render_summary(console, deployments, configs, findings):
    """One row per deployment: how big it is, when it last moved, what is wrong with it."""
    by_subject = defaultdict(Counter)
    for finding in findings:
        for subject in finding.subjects:
            by_subject[subject][finding.kind] += 1

    # One narrow column per check that actually fired, so the table stays a scannable
    # matrix rather than a paragraph of labels per row. Checks with no chain attribution
    # (CONTRACTS is repo-wide) never appear here.
    present = [k for k in KIND_ORDER if any(k in counts for counts in by_subject.values())]

    table = Table(box=box.SIMPLE_HEAD, pad_edge=False, header_style="bold")
    table.add_column("chain", no_wrap=True)
    table.add_column("n", justify="right")
    table.add_column("deployed", no_wrap=True)
    for kind in present:
        table.add_column(KIND_ABBREV[kind], justify="right", style=KIND_STYLE[kind])

    missing_config = False
    for key, (path, raw) in sorted(deployments.items()):
        rows = list(contract_rows(raw))
        stamps = [r["deployment_timestamp"] for _, r in rows if isinstance(r.get("deployment_timestamp"), int)]
        last = datetime.fromtimestamp(max(stamps), tz=timezone.utc).strftime("%Y-%m-%d") if stamps else "-"
        no_config = key not in configs
        missing_config |= no_config

        counts = by_subject.get(key, Counter())
        table.add_row(
            f"{key}[red]*[/]" if no_config else key,
            str(len(rows)),
            last,
            *[str(counts[k]) if counts.get(k) else "[dim].[/]" for k in present],
        )

    # Chain configs that never produced a deployment have no row above; list them so the
    # table is a complete picture of the repo rather than of deployments only.
    console.print(table)
    legend = ["n = contract rows recorded"]
    if missing_config:
        # emit() escapes markup, so keep the legend plain text.
        legend.append("* = no settings/chains config, cannot be re-run")
    if undeployed := sorted(set(configs) - set(deployments)):
        legend.append(f"not deployed: {' '.join(undeployed)}")
    for line in legend:
        emit(console, line, indent=2, style="dim")
    console.print("")


@click.command("status", short_help="deployment status and drift report")
@click.option("--chain", metavar="NAME", default=None, help="restrict to one chain")
@click.option("--only", type=click.Choice(CHECKS), default=None, help="run a single check")
@click.option("--onchain", is_flag=True, help="verify every recorded address has bytecode")
@click.option("--wiring", is_flag=True, help="check factory pointers and ownership on chain")
@click.option("--bytecode", is_flag=True, help="recompile and compare against deployed code (slow)")
@click.option("--summary", is_flag=True, help="one-row-per-chain table instead of full findings")
@click.option("--json", "json_path", metavar="PATH", default=None, help="write findings as JSON")
def status_command(chain, only, onchain, wiring, bytecode, summary, json_path):
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

    # Run CONFIG first so REQUIRED can attribute inherited failures to it.
    broken_configs = {f.subjects[0] for f in check_config(configs, selected) if f.subjects}

    runners = {
        "pending": lambda: check_pending(deployments),
        "config": lambda: check_config(configs, selected),
        "contracts": check_contracts,
        "schema": lambda: check_schema(deployments),
        "required": lambda: check_required(deployments, broken_configs),
        "coverage": lambda: check_coverage(everything, configs, selected),
        "integrity": lambda: check_integrity(deployments),
    }
    # CONTRACTS inspects contracts/ and abi/, which belong to no chain - including it in a
    # --chain report would attribute repo-wide problems to that chain.
    repo_wide = {"contracts"}
    findings = []
    for name in CHECKS:
        if only not in (None, name):
            continue
        if chain and name in repo_wide and only != name:
            continue
        findings += runners[name]()
    if onchain:
        findings += check_onchain(deployments)
    if wiring:
        findings += check_wiring(deployments)
    if bytecode:
        findings += check_bytecode(deployments)

    by_kind = defaultdict(list)
    for finding in findings:
        by_kind[finding.kind].append(finding)

    if summary:
        if only:
            # Otherwise the empty columns read as "those checks passed".
            emit(console, f"only the {only} check ran - other columns are not shown", indent=2, style="yellow")
        render_summary(console, deployments, configs, findings)

    for kind in KIND_ORDER if not summary else ():
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
