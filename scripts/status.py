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
             through model_dump(). Also reports the reverse: config keys curve-api-core
             reads that no deployment writes.
  REQUIRED   Runs DeploymentConfig.model_validate() and reports pydantic's own errors -
             a file that fails here cannot be read or updated by the deployer at all.
  COVERAGE   Chain configs with no deployment, deployments with no chain config, and
             file_name collisions (that field is curve-api-core's blockchain id).
  INTEGRITY  Admin roles that are null, shared between roles, or collapsed onto one
             address.

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
import subprocess
import sys
import textwrap
import types
import urllib.error
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

from scripts.deploy.deployment_file import BLUEPRINT_VERSION_PATTERN
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
    "SCHEMA": "keys the models and curve-api-core disagree about - dropped on round-trip, or expected and never written",
    "REQUIRED": "model_validate() raises - the deployer cannot read or update these chains",
    "COVERAGE": "deployments and chain configs that do not line up",
    "INTEGRITY": "admin roles that are missing, shared, or collapsed onto one address",
    "ONCHAIN": "recorded addresses checked against chain state",
    "WIRING": "on-chain wiring and ownership vs what the deployment file records",
    "BYTECODE": "recompiled source vs the code actually deployed",
}


def rel(path):
    """Path for display. Absolute when it is outside the repo, rather than raising."""
    try:
        return Path(path).relative_to(BASE_DIR).as_posix()
    except ValueError:
        return str(path)


def plural(count, noun):
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def emit(console, text, indent=0, style="", bullet="", bullet_style=""):
    """Print `text` wrapped to the terminal with every continuation line aligned under the
    first. rich.Padding would do the indent but pads each wrapped line out to the block
    width, leaving trailing whitespace in redirected output - so wrap here instead.

    `bullet_style` colours the bullet independently of the body, so --brief can tag a line
    with its kind without colouring the whole summary."""
    body_indent = indent + len(bullet)
    width = max(40, console.width - body_indent)
    lines = textwrap.wrap(text, width=width) or [""]
    for number, line in enumerate(lines):
        pad = " " * indent
        if number == 0 and bullet:
            pad += f"[{bullet_style}]{escape(bullet)}[/]" if bullet_style else bullet
        else:
            pad += " " * len(bullet)
        console.print(f"{pad}[{style}]{escape(line)}[/]" if style else f"{pad}{escape(line)}")


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
    unverified: bool = False  # "could not check", not "found a problem" - shown as ? not a count


# --------------------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------------------


def load_deployments(only_chain: str | None = None) -> tuple[dict[str, tuple[Path, dict]], dict]:
    """Raw YAML per deployment file, keyed "env/stem" (prod/sonic), plus the files that
    are not parseable at all.

    Keyed by path rather than config.file_name because prod and devnet files routinely
    share a file_name - keying on it drops one of every such pair, which is exactly the
    collision COVERAGE reports downstream.

    Deliberately not YamlDeploymentFile.get_deployment_config(), which validates: some
    files fail validation and those are precisely what REQUIRED exists to report.

    A file that is not valid YAML is returned, not raised: reporting broken deployment
    files is the whole job, so meeting one must not take the other 26 chains down with it.
    """
    out, unreadable = {}, {}
    for path in sorted((BASE_DIR / "deployments").rglob("*.yaml")):
        if {"debug", "examples"} & set(path.parts):
            continue  # dry-run output and templates, not real deployments
        key = f"{path.parent.name}/{path.stem}"
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            # Only key and stem can match here - file_name lives inside the file.
            if not only_chain or only_chain in (key, path.stem):
                unreadable[key] = (path, exc)
            continue
        name = (raw.get("config") or {}).get("file_name") or path.stem
        if only_chain and only_chain not in (key, name, path.stem):
            continue
        out[key] = (path, raw)
    return out, unreadable


def chain_configs() -> dict[str, Path]:
    """Keyed "env/stem" (prod/sonic, devnet/sonic) the way config.file_path is, because a
    chain can legitimately have both a prod and a devnet config - keying on the bare stem
    silently drops one of every such pair."""
    root = BASE_DIR / "settings" / "chains"
    return {f"{p.parent.name}/{p.stem}": p for p in root.rglob("*.yaml") if "examples" not in p.parts}


def legacy_deployments(deployments, configs) -> set:
    """Chains recorded here but never deployed by this repo - out of scope for every check.

    avalanche, fantom and x_layer were full-Curve deployments later deprecated to Lite; their
    rows are hand-written, with no contract_path or compiler metadata. Detected by shape - no
    chain config and no provenance on any row - rather than by a hardcoded list, so a future
    one is classified automatically.
    """
    legacy = set()
    for chain, (_, raw) in deployments.items():
        if chain in configs:
            continue
        rows = list(contract_rows(raw))
        if rows and not any(row.get("contract_path") for _, row in rows):
            legacy.add(chain)
    return legacy


def in_scope(deployments, configs) -> tuple[dict, set]:
    """(kept, skipped) - what curve-core deploys, and what predates it.

    The single definition of scope. `status` and `index` both call it, so the report cannot
    cover a different set of chains than the published index.
    """
    skipped = legacy_deployments(deployments, configs)
    return {key: value for key, value in deployments.items() if key not in skipped}, skipped


def example_configs() -> dict[str, Path]:
    """The onboarding templates, kept apart from real chains so COVERAGE does not report
    them as configs that were never deployed."""
    root = BASE_DIR / "settings" / "chains" / "examples"
    return {f"examples/{p.stem}": p for p in sorted(root.glob("*.yaml"))}


def contract_rows(raw: dict):
    """Yield (dotted_slot, row) for every contract entry, valid or not.

    Keeps descending after a hit: registry_handlers sits *inside* the metaregistry row,
    which has an address of its own, so returning early hides the three handler rows on
    every chain from every check that walks contracts.
    """

    def walk(node, trail):
        if not isinstance(node, dict):
            return
        if "address" in node:
            yield ".".join(trail), node
        for key, value in node.items():
            yield from walk(value, trail + [key])

    yield from walk(raw.get("contracts") or {}, [])


def norm(addr):
    return addr.lower() if isinstance(addr, str) and addr.startswith("0x") else None


# --------------------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------------------


# scripts/deploy/governance/xgov.py pins the agent to v_100 on these rollups (the 0.4.0
# agent is not deployable there), and deploy_contract's pinned branch skips the version
# comparison entirely - so "latest wins" does not hold for that slot.
XGOV_PINNED_ROLLUPS = frozenset({"arb_orbit", "op_stack", "polygon_cdk"})
PINNED_AGENT_VERSION = "1.0.0"
XGOV_SLOTS = ("governance.agent", "governance.relayer")


def _xgov_plan(raw, config_path):
    """(xgov_runs, pinned_agent_version) for a chain, mirroring run_deploy_all + xgov.py.

    run_deploy_all skips xgov entirely when the chain config presets all three DAO admins,
    so nothing under governance.* is touched on those chains no matter what sits in
    contracts/. Read the *chain config*, not the deployment file: once xgov has run it
    writes the agent addresses back into the deployment's dao block, which then looks
    identical to a preset.
    """
    source = raw
    if config_path is not None:
        try:
            source = {"config": yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}}
        except OSError:
            source = raw
    config = source.get("config") or {}
    dao = config.get("dao") or {}
    presets_all_admins = all(dao.get(role) for role in ("ownership_admin", "parameter_admin", "emergency_admin"))
    pinned = PINNED_AGENT_VERSION if config.get("rollup_type") in XGOV_PINNED_ROLLUPS else None
    return (not presets_all_admins), pinned


def check_pending(deployments, configs=None, blocked=()):
    """What the next `deploy all` would upgrade, using the deployer's own resolution.

    `blocked` maps chain -> why `deploy all` cannot run on it today ("rejected": its
    settings/chains file exists but ChainConfig refuses it; "missing": there is no such
    file). They are still listed - the upgrade is real and lands the moment the blocker
    clears - but called out, because saying they upgrade "automatically" is false today.
    """
    configs = configs or {}
    blocked = dict(blocked)
    grouped, malformed, pinned_drift = defaultdict(list), [], []
    for chain, (_, raw) in deployments.items():
        xgov_runs, pinned_agent = _xgov_plan(raw, configs.get(chain))
        for slot, row in contract_rows(raw):
            contract_path, recorded = row.get("contract_path"), row.get("contract_version")
            if not contract_path or not recorded:
                continue

            if slot.startswith(XGOV_SLOTS):
                if not xgov_runs:
                    continue  # deploy_all never reaches xgov on this chain
                if slot == "governance.agent" and pinned_agent:
                    # The pinned branch takes the named file regardless of what is newer,
                    # and regardless of what is already deployed. Report only the case that
                    # actually changes state: a record that disagrees with the pin.
                    if normalise_version(str(recorded)) != pinned_agent:
                        pinned_drift.append((chain, recorded))
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
                # A version that is not digits-and-dots (e.g. "1.0.0rc1") breaks the deployer
                # itself, not just this report.
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

    # "cannot be deployed at all right now" left the reader to work out what was blocked,
    # why, and what it meant for this row. Say all three: the command that will not run, the
    # cause and where it is fixed, and the version these chains keep in the meantime.
    CAUSES = (
        (
            "rejected",
            "its settings/chains file is rejected by ChainConfig (see CONFIG)",
            "their settings/chains files are rejected by ChainConfig (see CONFIG)",
        ),
        (
            "missing",
            "it has no settings/chains file at all (see COVERAGE)",
            "they have no settings/chains file at all (see COVERAGE)",
        ),
    )

    def chain_lines(chains, old):
        """One labelled line per group, each chain named exactly once.

        The affected chains used to be printed as a bare unlabelled list after the blocked
        ones had already been called out by name, so the blocked chains appeared twice and
        the list read as a continuation of that sentence rather than as the full set.
        """
        stuck = set(chains) & set(blocked)
        lines = []
        for cause, one, many in CAUSES:
            members = sorted(c for c in stuck if blocked[c] == cause)
            if not members:
                continue
            single = len(members) == 1
            lines.append(
                f"{len(members)} of these cannot run `deploy all` today and "
                f"{'stays' if single else 'stay'} on {old} until that is fixed: "
                f"{one if single else many} - {', '.join(members)}"
            )
        ready = sorted(set(chains) - stuck)
        if ready:
            lead = f"the other {len(ready)}" if stuck else f"all {len(ready)}"
            lines.append(f"{lead} upgrade on the next run: {' '.join(ready)}")
        return tuple(lines)

    findings = [
        Finding(
            "PENDING",
            f"{fname}  {old} -> {new}  ({scale(chains)})",
            f"slot {slot}",
            details=chain_lines(chains, old),
            subjects=tuple(sorted(chains)),
        )
        for (slot, old, new, fname), chains in sorted(grouped.items(), key=lambda kv: -len(kv[1]))
    ]
    for chain, recorded in sorted(pinned_drift):
        findings.append(
            Finding(
                "PENDING",
                f"{chain}: governance.agent would be re-recorded {recorded} -> {PINNED_AGENT_VERSION}",
                f"xgov.py pins the agent to v_100 on {'/'.join(sorted(XGOV_PINNED_ROLLUPS))}, so a "
                f"re-run overwrites this record with the older version - a downgrade the "
                f"latest-wins rule never surfaces",
                subjects=(chain,),
            )
        )
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


# config.* keys curve-api-core reads (constants/configs/configs.js). A key it reads that
# nothing writes is served as undefined; walking the models only finds keys that ARE present.
API_CONSUMED_CONFIG_KEYS = (
    "file_name",
    "network_name",
    "chain_id",
    "explorer_base_url",
    "multicall2",
    "multicall3",
    "native_currency_symbol",
    "native_currency_coingecko_id",
    "platform_coingecko_id",
    "public_rpc_url",
)


def check_schema(deployments):
    unknown = defaultdict(set)
    for chain, (_, raw) in deployments.items():
        for key in _undeclared(raw, DeploymentConfig):
            unknown[key].add(chain)

    # The reverse direction: fields the consumer expects and nobody produces.
    written = {key for _, (_, raw) in deployments.items() for key in (raw.get("config") or {})}
    absent = [key for key in API_CONSUMED_CONFIG_KEYS if key not in written]
    extra = (
        [
            Finding(
                "SCHEMA",
                f"config.{key} is read by curve-api-core but written by no chain",
                "served as undefined for every chain; walking the models cannot catch this, "
                "since it only sees keys that are present",
            )
            for key in absent
        ]
        if deployments
        else []
    )

    return extra + [
        Finding(
            "SCHEMA",
            f"{key}  ({plural(len(chains), 'chain')})",
            "",
            tuple(sorted(chains)),
            subjects=tuple(sorted(chains)),
        )
        for key, chains in sorted(unknown.items())
    ]


def config_errors(configs, selected=None):
    """{chain: [pydantic error, ...]} for every chain config that fails to load.

    Shared by CONFIG (which reports them) and REQUIRED (which needs the exact fields to
    decide whether a deployment error really is inherited from its config).
    """
    out = {}
    for key, path in sorted(configs.items()):
        if selected and key not in selected:
            continue
        try:
            get_chain_settings(path.relative_to(BASE_DIR / "settings" / "chains").as_posix())
        except ValidationError as exc:
            out[key] = exc.errors()
        except Exception as exc:  # unreadable yaml, missing file, ...
            out[key] = [{"loc": (), "type": "unloadable", "msg": f"{type(exc).__name__}: {exc}"}]
    return out


def check_config(configs, selected=None):
    """Validate the deploy *inputs*. REQUIRED covers deployment files, but a chain config
    that ChainConfig rejects fails at get_chain_settings() before a deploy even starts -
    and since the config is copied into the deployment file, it is often the root cause
    of the matching REQUIRED finding."""
    findings = []
    for key, errors in config_errors(configs, selected).items():
        path = configs[key].relative_to(BASE_DIR).as_posix()
        if errors and errors[0]["type"] == "unloadable":
            findings.append(Finding("CONFIG", f"{key}: cannot be loaded", errors[0]["msg"], subjects=(key,)))
            continue
        findings.append(
            Finding(
                "CONFIG",
                f"{key}  ({plural(len(errors), 'error')})",
                path,
                (),
                _summarise_errors(errors),
                subjects=(key,),
            )
        )

    # The templates are what a new chain is told to copy, so an invalid one breaks onboarding
    # before anything else. Nothing checked them until now.
    if not selected:
        for key, errors in config_errors(example_configs()).items():
            findings.append(
                Finding(
                    "CONFIG",
                    f"{key}  ({plural(len(errors), 'error')}) - onboarding template",
                    f"{configs_path(key)} is what README tells a new chain to copy",
                    (),
                    _summarise_errors(errors),
                )
            )
    return findings


def configs_path(key):
    return f"settings/chains/{key}.yaml"


# Imported, not mirrored - a local copy had drifted and produced false negatives.
# ANY_VERSION_RE is loose on purpose: it reports what was declared, including refused forms.
BLUEPRINT_VERSION_RE = BLUEPRINT_VERSION_PATTERN
ANY_VERSION_RE = re.compile(r'version:\s*public\(constant\(String\[8\]\)\)\s*=\s*"([^"]+)"')


def check_contracts():
    """Static problems in contracts/ and abi/ that only surface mid-deploy today."""
    findings = []
    contracts_dir = BASE_DIR / "contracts"

    # unparseable: deploy raises immediately. mismatched: deploy succeeds and records a
    # version contradicting the filename fetch_latest_contract sorts on - silent, and worse.
    unparseable, mismatched, no_version = [], [], []
    for source in sorted(contracts_dir.rglob("*_v_*.vy")):
        shown = source.relative_to(BASE_DIR).as_posix()
        digits = re.search(r"_v_(\d+)\.vy$", source.name).group(1)
        implied = ".".join(digits) if len(digits) == 3 else digits
        text = source.read_text(encoding="utf-8")
        declared = ANY_VERSION_RE.search(text)
        if declared is None:
            no_version.append(shown)
        elif not BLUEPRINT_VERSION_RE.search(text):
            unparseable.append(f"{shown}: declares {declared.group(1)!r}")
        elif normalise_version(declared.group(1)) != implied:
            mismatched.append(f"{shown}: declares {declared.group(1)!r}, filename implies {implied!r}")

    # fetch_latest_contract sorts a folder on _v_NNN alone, so two unrelated contracts in one
    # folder compete for the slot. PENDING would report the swap as an ordinary upgrade.
    shared = []
    for folder in sorted({f.parent for f in contracts_dir.rglob("*_v_*.vy")}):
        by_stem = defaultdict(list)
        for source in folder.glob("*_v_*.vy"):
            if re.search(r"_v_(\d+)\.vy$", source.name):
                by_stem[source.name.rsplit("_v_", 1)[0]].append(source)
        if len(by_stem) < 2:
            continue
        try:
            winner = fetch_latest_contract(folder).name
        except (FileNotFoundError, ValueError):
            continue
        losers = sorted(s.name for group in by_stem.values() for s in group if s.name != winner)
        shared.append(
            f"{folder.relative_to(BASE_DIR).as_posix()}/: {len(by_stem)} unrelated contracts "
            f"share this slot, {winner} wins it today over {', '.join(losers)}"
        )
    if shared:
        findings.append(
            Finding(
                "CONTRACTS",
                f"{plural(len(shared), 'folder')} holding more than one contract",
                "fetch_latest_contract picks the highest _v_NNN in a folder regardless of which "
                "contract it belongs to, so adding a higher-numbered version of the other one "
                "silently swaps what every chain deploys into that slot",
                (),
                tuple(shared),
            )
        )

    # fetch_latest_contract only ever considers files matching *_v_NNN.vy, so anything else
    # in contracts/ is unreachable: the deployer cannot select it no matter what.
    unreachable = sorted(
        f.relative_to(BASE_DIR).as_posix() for f in contracts_dir.rglob("*.vy") if not re.search(r"_v_\d+\.vy$", f.name)
    )
    if unreachable:
        findings.append(
            Finding(
                "CONTRACTS",
                f"{plural(len(unreachable), 'contract')} the deployer can never select",
                "fetch_latest_contract only matches *_v_NNN.vy, so these are invisible to it "
                "and cannot be deployed until renamed",
                (),
                tuple(unreachable),
            )
        )
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


def check_required(deployments, broken_configs=(), unreadable=()):
    """Pydantic's own verdict - these files cannot be loaded by the deployer at all.

    `broken_configs` lets a finding point at its cause: the deployer copies the chain
    config into the deployment file, so an invalid config reappears here as an invalid
    deployment. Reporting both without linking them counts one mistake twice.

    `unreadable` never reached pydantic - the YAML itself does not parse.
    """
    findings = []
    for chain, (path, exc) in sorted(dict(unreadable).items()):
        mark = getattr(exc, "problem_mark", None)
        where = f"line {mark.line + 1}" if mark else "unknown line"
        findings.append(
            Finding(
                "REQUIRED",
                f"{chain}  (not valid YAML)",
                path.relative_to(BASE_DIR).as_posix(),
                (),
                (f"{where}: {getattr(exc, 'problem', None) or exc}",),
                subjects=(chain,),
            )
        )
    for chain, (path, raw) in sorted(deployments.items()):
        try:
            DeploymentConfig.model_validate(raw)
        except ValidationError as exc:
            errors = exc.errors()
            note = path.relative_to(BASE_DIR).as_posix()
            # Match on fields, not chains: neon/taiko fail CONFIG and REQUIRED on different
            # fields, and were previously mislabelled as inherited.
            from_config = {".".join(str(p) for p in e["loc"]) for e in broken_configs.get(chain, ())}
            here = {".".join(str(p) for p in e["loc"][1:]) for e in errors if e["loc"][:1] == ("config",)}
            shared = from_config & here
            if shared and shared == here:
                note += "  (inherited from the CONFIG finding above, not a separate mistake)"
            elif shared:
                note += f"  ({', '.join(sorted(shared))} inherited from CONFIG; the rest are not)"
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

    # config.file_name is curve-api-core's blockchain id, so two *different* chains sharing
    # one means the second is invisible downstream. A chain's own devnet/prod pair is not
    # that: Lite chains are deployed to their testnet first and keep the name, and the API
    # separates them by folder. Only report names shared by genuinely different chains.
    by_name = defaultdict(list)
    for path, raw in deployments.values():
        by_name[(raw.get("config") or {}).get("file_name") or path.stem].append(path.relative_to(BASE_DIR).as_posix())
    clashes = {
        name: paths
        for name, paths in by_name.items()
        if len({Path(p).stem for p in paths}) > 1 or len({Path(p).parent.name for p in paths}) < len(paths)
    }
    if selected:
        # Under --chain, report only the collision the selected chain is part of - it is
        # about that chain, so suppressing it entirely hid the finding that mattered most.
        clashes = {
            name: paths
            for name, paths in clashes.items()
            if any(f"{Path(p).parent.name}/{Path(p).stem}" in selected for p in paths)
        }
    if clashes:
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


ADMIN_ROLES = ("ownership_admin", "parameter_admin", "emergency_admin")


def check_integrity(deployments):
    by_addr = defaultdict(list)
    partial, ungoverned = [], []
    for chain, (_, raw) in sorted(deployments.items()):
        dao = (raw.get("config") or {}).get("dao") or {}
        admins = {k: norm(v) for k, v in dao.items() if k.endswith("_admin") and norm(v)}
        if not admins and any(role in dao for role in ADMIN_ROLES):
            # Every admin recorded as null: the file names no governance at all for a
            # chain with contracts on it.
            ungoverned.append(chain)
            continue
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
    if ungoverned:
        findings.append(
            Finding(
                "INTEGRITY",
                f"{plural(len(ungoverned), 'chain')} with no admin recorded at all",
                "every admin role is null, so the deployment file names nobody who can "
                "administer these contracts - and update_address_provider writes those "
                "nulls into ids 21/22/23",
                tuple(ungoverned),
                subjects=tuple(ungoverned),
            )
        )
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
                # The address belongs in the summary, not just the note: it is the only
                # thing telling these rows apart, and --brief and --json show summaries.
                f"{plural(len(chains), 'chain')}: one address holds every admin role - {addr}",
                note,
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
        try:
            # Must go through _rpc_call: a hand-rolled .get("result") turns an in-band
            # {"error": ...} (rate limit, unsupported method) into None, which the caller
            # cannot tell from "no bytecode" - i.e. it accuses a live chain of being a ghost.
            return chain, slot, addr, _rpc_call(rpc, "eth_getCode", [addr, "latest"]), None
        except Exception as exc:
            return chain, slot, addr, None, _error_label(exc)

    ghosts, errors, probed = defaultdict(list), defaultdict(Counter), Counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(probe, job) for job in jobs]):
            chain, slot, addr, code, failure = future.result()
            probed[chain] += 1
            if failure:
                errors[chain][failure] += 1
            elif code in (None, "0x"):
                ghosts[chain].append(f"{slot} {addr}")

    findings = [
        Finding(
            "ONCHAIN",
            f"{chain}: {len(rows)}/{probed[chain]} recorded "
            f"{'address has' if len(rows) == 1 else 'addresses have'} NO bytecode",
            "recorded but never deployed",
            tuple(sorted(rows)),
            subjects=(chain,),
        )
        for chain, rows in sorted(ghosts.items())
    ]
    # A dead public RPC is infrastructure noise, not a deployment finding. Name the reason:
    # every probe failing usually means back off and re-run, some probes failing usually
    # means the endpoint is fine and those addresses are the problem.
    findings += [
        Finding(
            "ONCHAIN",
            f"{chain}: unverified, RPC failed on {sum(labels.values())}/{probed[chain]} "
            f"probes ({_dominant(labels)})",
            (
                "every probe failed - public_rpc_url is dead, or rate-limited by an earlier "
                "run; re-run after a pause before believing it"
                if sum(labels.values()) == probed[chain]
                else "some probes failed - no conclusion drawn for those addresses"
            ),
            subjects=(chain,),
            unverified=True,
        )
        for chain, labels in sorted(errors.items())
    ]
    return findings


class RpcError(RuntimeError):
    """A JSON-RPC call that answered, but with an error object instead of a result."""


def _rpc_call(rpc, method, params, timeout=25):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(
        rpc, data=body, headers={"content-type": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    # A rate-limited or unsupported call answers HTTP 200 with {"error": ...}. Returning
    # .get("result") would hand back None, which eth_getCode callers cannot tell apart
    # from "no bytecode" - i.e. it would accuse a live chain of being a ghost.
    if isinstance(payload, dict) and payload.get("error") is not None:
        raise RpcError(str(payload["error"])[:120])
    if not isinstance(payload, dict) or "result" not in payload:
        raise RpcError("response contained no result")
    return payload["result"]


def _error_label(exc):
    """A short, aggregatable reason a probe failed.

    "RPC failed on 24/24 probes" cannot be acted on: rate-limiting, a dead endpoint and a
    method the node does not implement all read the same, and only the first is worth
    re-running later. The exception type alone does not separate them either - HTTP 429 and
    HTTP 503 are both HTTPError - so keep the status code, which is the part that says
    whether to back off or fix the URL.
    """
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError):
            return "timeout"
        return f"unreachable ({type(reason).__name__})" if isinstance(reason, Exception) else "unreachable"
    if isinstance(exc, TimeoutError):
        return "timeout"
    if isinstance(exc, RpcError):
        # The node's own message is the actionable part ("rate limit exceeded", "method not
        # found"), but it varies enough between providers to fragment a Counter, so trim it.
        return f"RPC error: {str(exc)[:40]}"
    return type(exc).__name__


def _dominant(labels):
    """`labels` -> "reason" or "reason and N other kinds", for a one-line finding."""
    if not labels:
        return ""
    (top, _), rest = labels.most_common(1)[0], len(labels) - 1
    return f"{top} and {plural(rest, 'other kind')}" if rest else top


def _eth_call(rpc, to, signature, argument=None):
    data = "0x" + keccak(text=signature).hex()[:8]
    if argument is not None:
        data += f"{argument:064x}"
    return _rpc_call(rpc, "eth_call", [{"to": to, "data": data}, "latest"])


def _as_address(result):
    return "0x" + result[-40:].lower() if isinstance(result, str) and len(result) >= 42 else None


# Deployed code is not the compiler's runtime output verbatim: normal contracts append
# immutables and ctor args (so match by prefix); blueprints carry a 10-byte EIP-5202 wrapper.
BLUEPRINT_WRAPPER_BYTES = 10

# The commit contract_github_url pins. Vendored sources are edited in place while the version
# constant stays put, so contract_path + contract_version do not identify what was deployed.
DEPLOY_COMMIT_RE = re.compile(r"/blob/([0-9a-f]{7,40})/")


def _git(*args):
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=BASE_DIR)
    return result.stdout.strip() if result.returncode == 0 else None


def source_provenance(row):
    """(state, source) for a row, where state is why it can or cannot be compared.

    "current"   - the file has not changed since the deploy commit, so compiling it is valid
    "drifted"   - it has changed; comparing against today's file proves nothing
    "unpinned"  - no usable commit recorded, so drift cannot be ruled out
    "unreachable" - the commit is not in this clone (shallow, or rewritten history)
    """
    path = str(row.get("contract_path") or "").lstrip("/")
    match = DEPLOY_COMMIT_RE.search(str(row.get("contract_github_url") or ""))
    if not path or not match:
        return "unpinned", None
    commit = match.group(1)
    then, now = _git("rev-parse", f"{commit}:{path}"), _git("rev-parse", f"HEAD:{path}")
    if then is None:
        return "unreachable", None
    if then == now:
        return "current", None
    return "drifted", _git("show", f"{commit}:{path}")


def check_bytecode(deployments, workers=8, from_commit=False):
    """Recompile each recorded contract and compare against the code actually on chain.

    This is the only check that proves contract_path / contract_version / evm_version
    describe what was really deployed - everything else trusts the deployment file.
    """
    compiled: dict[tuple, dict] = {}
    missing_compilers = set()

    def compile_row(row, source_text=None):
        settings = row.get("compiler_settings") or {}
        version, evm = settings.get("compiler_version"), settings.get("evm_version")
        if not version:
            # Hand-written catalog rows record nothing about how they were built, so there
            # is no source to recompile. Say so rather than crashing on a null path below.
            raise ValueError("no compiler_version recorded - cannot recompile")
        source = BASE_DIR / Path(str(row["contract_path"]).lstrip("/"))
        key = (str(source), version, evm, hash(source_text))
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
                source_text if source_text is not None else source.read_text(encoding="utf-8"),
                vyper_binary=binary,
                base_path=BASE_DIR,
                evm_version=evm,
            )["<stdin>"]
        return compiled[key]

    jobs = []
    # Rows carrying an address but no provenance (the hand-written catalog chains) cannot
    # be recompiled. They used to be filtered out here and never mentioned, so a chain
    # could report "nothing to report" having had most of its rows silently skipped.
    unprovenanced = defaultdict(list)
    for chain, (_, raw) in deployments.items():
        rpc = (raw.get("config") or {}).get("public_rpc_url")
        if not rpc:
            continue
        for slot, row in contract_rows(raw):
            if not norm(row.get("address")):
                continue
            if not row.get("contract_path") or not (row.get("compiler_settings") or {}).get("compiler_version"):
                unprovenanced[chain].append(slot)
                continue
            jobs.append((chain, slot, row, rpc))

    # Compile serially (cached, CPU-bound, and vvm shells out) but fetch code concurrently.
    expected, drifted = {}, defaultdict(list)
    for chain, slot, row, _ in jobs:
        # A vendored source edited after the deploy makes today's file the wrong artifact to
        # compare against - the mismatch would be ours, not the chain's. Report it as
        # unverifiable unless --from-commit is on, which compiles what was actually deployed.
        state, historical = source_provenance(row)
        if state != "current" and not from_commit:
            drifted[chain].append((slot, state))
            continue
        try:
            output = compile_row(row, historical if state == "drifted" else None)
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
            return chain, slot, row, _rpc_call(rpc, "eth_getCode", [norm(row["address"]), "latest"]), None
        except Exception as exc:
            return chain, slot, row, None, _error_label(exc)

    mismatched, uncompilable, unreachable = defaultdict(list), [], defaultdict(Counter)
    comparable = [j for j in jobs if (j[0], j[1]) in expected]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for future in as_completed([pool.submit(probe, job) for job in comparable]):
            chain, slot, row, code, failure = future.result()
            kind, want = expected[(chain, slot)]
            if kind == "error":
                uncompilable.append(f"{chain} {slot}: {want}")
                continue
            if failure or not isinstance(code, str):
                unreachable[chain][failure or "no result"] += 1
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
            f"{chain}: {plural(len(slots), 'contract')} "
            f"{'does not match its' if len(slots) == 1 else 'do not match their'} recorded source",
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
    findings += [
        Finding(
            "BYTECODE",
            f"{chain}: {plural(len(slots), 'row')} skipped, no contract_path/compiler_version to rebuild from",
            "hand-written catalog rows record nothing about how they were built, so nothing "
            "about them can be verified against chain",
            tuple(sorted(slots)),
            subjects=(chain,),
            unverified=True,
        )
        for chain, slots in sorted(unprovenanced.items())
    ]
    if other := [line for line in uncompilable if "no local vyper" not in line]:
        shown = sorted(other)[:10]
        findings.append(
            Finding(
                "BYTECODE",
                f"{plural(len(other), 'contract')} could not be recompiled to compare",
                # Say what was truncated: a silently shortened list reads as the whole set,
                # which would understate how much of a chain went unchecked.
                "" if len(other) == len(shown) else f"showing {len(shown)} of {len(other)}",
                (),
                tuple(shown),
                unverified=True,
            )
        )
    REASONS = {
        "drifted": "contract_path was edited after this deploy",
        "unpinned": "no commit recorded in contract_github_url",
        "unreachable": "the recorded commit is not in this clone",
    }
    for chain, rows in sorted(drifted.items()):
        why = Counter(state for _, state in rows)
        findings.append(
            Finding(
                "BYTECODE",
                f"{chain}: unverified, {plural(len(rows), 'row')} cannot be compared "
                f"({_dominant(Counter({REASONS[s]: n for s, n in why.items()}))})",
                "compiling the file at contract_path today would test the wrong source - "
                "re-run with --from-commit to compile what was actually deployed",
                tuple(sorted(slot for slot, _ in rows)),
                subjects=(chain,),
                unverified=True,
            )
        )
    findings += [
        Finding(
            "BYTECODE",
            f"{chain}: unverified, RPC failed on {plural(sum(labels.values()), 'probe')} " f"({_dominant(labels)})",
            "no conclusion drawn - back off and re-run if this is a rate limit",
            subjects=(chain,),
            unverified=True,
        )
        for chain, labels in sorted(unreachable.items())
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
            # Five values like every other exit - the caller unpacks five. A four-tuple here
            # was a ValueError waiting for the first chain without a public_rpc_url.
            return chain, [], [], Counter(), []
        wiring, ownership, unresolved, answered = [], [], [], 0
        # Count failed calls rather than swallowing them: a dead RPC must report
        # "unverified", never a clean bill of health. Keyed by reason so the finding can say
        # whether to back off and re-run or go fix the endpoint.
        failures = Counter()
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
                except Exception as exc:
                    failures[_error_label(exc)] += 1
                    continue
                # A codeless factory answers "0x", so _as_address gives None. That is not
                # agreement - it is nothing to compare, and must count as unverified.
                if live is None:
                    failures["empty response"] += 1
                elif live != recorded:
                    wiring.append(f"{group}.factory {signature[:-2]} -> {live}, recorded {slot} {recorded}")
            implementation = norm(((slots.get("implementation") or {}).get("address")) or "")
            if implementation:
                try:
                    live = _as_address(_eth_call(rpc, factory, "pool_implementations(uint256)", 0))
                except Exception as exc:
                    failures[_error_label(exc)] += 1
                else:
                    if live is None:
                        failures["empty response"] += 1
                    elif live != implementation:
                        wiring.append(f"{group}.factory pool_implementations(0) -> {live}, recorded {implementation}")

        owner = norm(((raw.get("config") or {}).get("dao") or {}).get("ownership_admin") or "")
        if owner:
            for slot, row in contract_rows(raw):
                if row.get("deployment_type") == "blueprint" or not norm(row.get("address")):
                    continue
                # Three outcomes must stay distinct: an answer, a transport failure, or no
                # usable answer - the last previously passed as if ownership were confirmed.
                resolved = None
                for signature in ("admin()", "owner()"):
                    try:
                        live = _as_address(_eth_call(rpc, norm(row["address"]), signature))
                    except Exception:
                        continue
                    if live is not None:
                        resolved = live
                        break
                if resolved is None:
                    unresolved.append(slot)
                else:
                    answered += 1
                    if resolved != owner:
                        # A zero owner is not "unowned, therefore fine" - it is a contract
                        # nobody can administer, which is worth saying out loud.
                        label = " (zero address - unownable)" if int(resolved, 16) == 0 else ""
                        ownership.append(f"{slot} owner={resolved}{label}")
        # Zaps/math/views expose no owner, so one unresolved row means nothing. Only *none*
        # resolving is genuinely unverifiable.
        if answered:
            unresolved = []
        return chain, wiring, ownership, failures, unresolved

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(inspect, (chain, raw)) for chain, (_, raw) in deployments.items()]
        for future in as_completed(futures):
            chain, wiring, ownership, failures, unresolved = future.result()
            if failures:
                findings.append(
                    Finding(
                        "WIRING",
                        f"{chain}: unverified, {plural(sum(failures.values()), 'call')} failed or "
                        f"returned nothing ({_dominant(failures)})",
                        "no conclusion drawn - an HTTP status points at the endpoint, "
                        "'empty response' at a target with no code",
                        subjects=(chain,),
                        unverified=True,
                    )
                )
            if unresolved:
                findings.append(
                    Finding(
                        "WIRING",
                        f"{chain}: ownership unverifiable - no contract answered admin() or owner()",
                        f"all {len(unresolved)} probed contracts returned nothing, so the chain is "
                        f"codeless or the endpoint is not answering; this is not evidence that "
                        f"ownership is correct",
                        (),
                        tuple(sorted(unresolved)),
                        subjects=(chain,),
                        unverified=True,
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


def render_summary(console, deployments, configs, findings, all_deployments=None):
    """One row per deployment: how big it is, when it last moved, what is wrong with it.

    `all_deployments` is the unfiltered set: under --chain the table shows one row, but
    "not deployed" must still be judged against every deployment, or every other chain in
    the repo gets listed as undeployed.
    """
    all_deployments = deployments if all_deployments is None else all_deployments
    by_subject = defaultdict(Counter)
    could_not_check = defaultdict(set)
    for finding in findings:
        for subject in finding.subjects:
            if finding.unverified:
                could_not_check[subject].add(finding.kind)
            else:
                by_subject[subject][finding.kind] += 1

    # One narrow column per check that actually fired, so the table stays a scannable
    # matrix rather than a paragraph of labels per row. Checks with no chain attribution
    # (CONTRACTS is repo-wide) never appear here.
    present = [
        k
        for k in KIND_ORDER
        if any(k in counts for counts in by_subject.values()) or any(k in kinds for kinds in could_not_check.values())
    ]

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
        skipped = could_not_check.get(key, set())

        def cell(kind, counts=counts, skipped=skipped):
            # "?" is not a smaller number than 1 - it means the check could not run here,
            # which a count would silently misrepresent as a clean or dirty result.
            if counts.get(kind):
                return str(counts[kind])
            return "[yellow]?[/]" if kind in skipped else "[dim].[/]"

        table.add_row(
            f"{key}[red]*[/]" if no_config else key,
            str(len(rows)),
            last,
            *[cell(k) for k in present],
        )

    # Chain configs that never produced a deployment have no row above; list them so the
    # table is a complete picture of the repo rather than of deployments only.
    console.print(table)
    legend = ["n = contract rows recorded"]
    if could_not_check:
        legend.append("? = check could not run for that chain (dead RPC, no code) - not a result")
    if missing_config:
        # emit() escapes markup, so keep the legend plain text.
        legend.append("* = no settings/chains config, cannot be re-run")
    undeployed = sorted(set(configs) - set(all_deployments))
    if len(deployments) < len(all_deployments):
        undeployed = [key for key in undeployed if key in deployments]  # scoped by --chain
    if undeployed:
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
@click.option(
    "--from-commit",
    is_flag=True,
    help="with --bytecode: compile each contract from the commit it was deployed at, not the current file",
)
@click.option("--summary", is_flag=True, help="one-row-per-chain table instead of full findings")
@click.option("--brief", is_flag=True, help="one line per finding, no explanations")
@click.option("--json", "json_path", metavar="PATH", default=None, help="write findings as JSON")
def status_command(chain, only, onchain, wiring, bytecode, from_commit, summary, brief, json_path):
    """Report what is deployed and what the next deploy would change."""
    if summary and brief:
        # Both replace the findings list with something else; there is no sensible merge.
        raise click.UsageError("--summary and --brief are alternative renderings, pick one")
    everything, _ = load_deployments()
    deployments, unreadable = load_deployments(chain)
    configs = chain_configs()

    # Scope is what curve-core deploys; index applies the same rule.
    everything, out_of_scope = in_scope(everything, configs)
    targeted_out_of_scope = bool(chain) and bool(set(deployments) & out_of_scope)
    deployments = {k: v for k, v in deployments.items() if k not in out_of_scope}
    if targeted_out_of_scope and not deployments:
        raise click.UsageError(f"{chain!r} was not deployed by this repo - out of scope")

    # A chain scaffolded by `init` has a config and no deployment yet.
    config_match = next((key for key in configs if chain in (key, key.split("/")[-1])), None) if chain else None
    if not deployments and not unreadable and not config_match:
        # UsageError exits 2, keeping "invoked wrong" apart from "drift found" (1) for CI.
        raise click.UsageError(f"no deployment or chain config found for {chain!r}")
    selected = (set(deployments) | set(unreadable) | ({config_match} if config_match else set())) if chain else None

    console = Console()
    prod = sum(1 for path, _ in deployments.values() if path.parent.name == "prod")
    scope = (
        f"chain {chain}"
        if chain
        else (f"{len(deployments)} deployments ({prod} prod, {len(deployments) - prod} devnet)")
    )
    console.print(f"[bold]curve-core status[/]  [dim]{scope}, {len(configs)} chain configs[/]\n")

    # Run CONFIG first so REQUIRED can attribute inherited failures to it.
    broken_configs = config_errors(configs, selected)
    # Chains `deploy all` cannot run on today, mapped to why. The two causes are disjoint -
    # config_errors only sees chains that have a config - and they are fixed in different
    # places, so PENDING names the cause rather than pointing at both sections at once.
    blocked = {chain: "rejected" for chain in broken_configs}
    blocked.update({chain: "missing" for chain in set(everything) - set(configs)})

    runners = {
        "pending": lambda: check_pending(deployments, configs, blocked),
        "config": lambda: check_config(configs, selected),
        "contracts": check_contracts,
        "schema": lambda: check_schema(deployments),
        "required": lambda: check_required(deployments, broken_configs, unreadable),
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
    # Track which on-chain checks actually ran, so a silent section can be reported as
    # "probed and clean" rather than being indistinguishable from "never ran".
    ran = []
    if onchain:
        findings += check_onchain(deployments)
        ran.append("ONCHAIN")
    if wiring:
        findings += check_wiring(deployments)
        ran.append("WIRING")
    if bytecode:
        findings += check_bytecode(deployments, from_commit=from_commit)
        ran.append("BYTECODE")

    by_kind = defaultdict(list)
    for finding in findings:
        by_kind[finding.kind].append(finding)

    if summary:
        if only:
            # Otherwise the empty columns read as "those checks passed".
            emit(console, f"only the {only} check ran - other columns are not shown", indent=2, style="yellow")
        render_summary(console, deployments, configs, findings, everything)

    if brief:
        # "Could not check" is not a result, so it is the first thing to drop - but it is
        # dropped out loud, because a shorter report that quietly hides what it skipped is
        # exactly the failure this tool exists to catch elsewhere.
        skipped = 0
        for kind in KIND_ORDER:
            for row in by_kind.get(kind, ()):
                if row.unverified:
                    skipped += 1
                    continue
                emit(console, row.summary, bullet=f"{kind:<10}", bullet_style=KIND_STYLE[kind])
        console.print("")
        if skipped:
            emit(
                console,
                f"{plural(skipped, 'finding')} hidden: the check could not run "
                f"(dead RPC, no code) - drop --brief to see them",
                style="dim italic",
            )
            console.print("")

    for kind in KIND_ORDER if not (summary or brief) else ():
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

    # An on-chain check that finds nothing prints nothing, which reads exactly like one
    # that was never enabled. Say which ones ran and came back clean.
    for kind in ran:
        if not by_kind.get(kind):
            emit(
                console,
                f"{kind}: {plural(len(deployments), 'chain')} probed, nothing to report",
                indent=0,
                style="green",
            )
    if ran and any(not by_kind.get(kind) for kind in ran):
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
    console.print(f"[bold]{plural(len(findings), 'finding')}[/]  {tally}")
    raise SystemExit(1)


if __name__ == "__main__":
    status_command()
