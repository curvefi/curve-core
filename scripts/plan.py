"""
What `deploy all` would do, without doing it.

    python manage.py deploy all prod/sonic.yaml --dry-run

Answers "will this work on my chain, and what would change" before anyone funds a wallet.
Needs no key, no RPC and no settings/env.

The step list below is ordered by hand because run_deploy_all's order is expressed in code,
not data. It is not trusted: deployer_folders() re-reads every deploy_contract() call site
in the deploy package, and any folder missing from the plan is reported rather than skipped.
"""

import re
from pathlib import Path

import click
import yaml

from scripts.deploy.utils import (
    fetch_filename_from_version,
    fetch_latest_contract,
    get_version_from_filename,
    normalise_version,
    version_a_gt_version_b,
)
from scripts.status import contract_rows, rel
from settings.config import BASE_DIR

DEPLOY_DIR = BASE_DIR / "scripts" / "deploy"
# Both spellings, so a new call site cannot hide from the staleness check.
CALL_SITES = (
    re.compile(r'Path\(\s*BASE_DIR\s*,\s*"contracts"\s*((?:,\s*"[^"]+"\s*)*)', re.S),
    re.compile(r'BASE_DIR\s*/\s*"contracts"\s*((?:/\s*"[^"]+"\s*)*)', re.S),
)

# deploy_xgov pins the agent to 0.3.10 on these rollups; agent_v_101.vy is 0.4.0.
AGENT_PIN = {"arb_orbit", "op_stack", "polygon_cdk"}

# In run_deploy_all order. Second element names the condition that skips the step.
STEPS = [
    ("governance/agent", "xgov"),
    ("governance/relayer/{rollup_type}", "xgov"),
    ("governance/vault", "vault"),
    ("gauge/child_gauge/factory", None),
    ("gauge/child_gauge/implementation", None),
    ("registries/address_provider", None),
    ("registries/metaregistry", None),
    ("registries/metaregistry/registry_handlers/stableswap", None),
    ("registries/metaregistry/registry_handlers/tricryptoswap", None),
    ("registries/metaregistry/registry_handlers/twocryptoswap", None),
    ("helpers/router", None),
    ("amm/stableswap/math", None),
    ("amm/stableswap/views", None),
    ("amm/stableswap/implementation", None),
    ("amm/stableswap/meta_implementation", None),
    ("amm/stableswap/factory", None),
    ("amm/tricryptoswap/math", None),
    ("amm/tricryptoswap/views", None),
    ("amm/tricryptoswap/implementation", None),
    ("amm/tricryptoswap/factory", None),
    ("amm/twocryptoswap/math", None),
    ("amm/twocryptoswap/views", None),
    ("amm/twocryptoswap/implementation", None),
    ("amm/twocryptoswap/factory", None),
    ("helpers/deposit_and_stake_zap", None),
    ("helpers/stable_swap_meta_zap", None),
    ("helpers/rate_provider", None),
]


def deployer_folders():
    """Every contracts/ folder passed to deploy_contract(), read from the source."""
    found = set()
    for path in sorted(DEPLOY_DIR.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for pattern in CALL_SITES:
            for match in pattern.finditer(source):
                parts = re.findall(r'"([^"]+)"', match.group(1))
                if parts:
                    found.add("/".join(parts))
    return found


def recorded_row(raw, slot):
    """The deployment file's row for a slot, or None. Same walker the checks use."""
    return dict(contract_rows(raw)).get(slot.replace("/", "."))


def plan_step(slot, raw, pinned=None):
    """(action, detail) for one folder, using the deployer's own resolution rules.

    `pinned` mirrors deploy_contract_version: the deployer skips fetch_latest_contract
    entirely for it, so reporting the newest file there would name the wrong contract.
    """
    folder = BASE_DIR / "contracts" / Path(slot)
    if not folder.is_dir():
        return "BLOCKED", "no such folder"
    try:
        latest = Path(fetch_filename_from_version(folder, pinned)) if pinned else fetch_latest_contract(folder)
    except (FileNotFoundError, IndexError):
        return "BLOCKED", f"no {pinned or '_v_NNN'} file the deployer can select"
    version = get_version_from_filename(latest)
    row = recorded_row(raw, slot)
    if not row or not row.get("address"):
        return "deploy", f"{latest.name}  {version}  (new)"
    current = row.get("contract_version")
    if row.get("address") and normalise_version(current or "") in ("", "0.0.0"):
        # deploy_contract raises here rather than redeploying over a live address.
        return "BLOCKED", f"recorded at {row['address'][:10]}... with contract_version={current!r}"
    if version_a_gt_version_b(version, current):
        return "deploy", f"{latest.name}  {current} -> {version}"
    return "reuse", f"{current}  {row['address'][:10]}..."


def build_plan(chain_settings, raw):
    """Ordered steps plus the two conditions run_deploy_all evaluates before contracts."""
    dao = chain_settings.dao
    skip = set()
    if dao and dao.ownership_admin and dao.parameter_admin and dao.emergency_admin:
        skip.add("xgov")
    if dao and dao.vault:
        skip.add("vault")

    steps = []
    for slot, condition in STEPS:
        slot = slot.format(rollup_type=chain_settings.rollup_type)
        if condition in skip:
            steps.append({"slot": slot, "action": "skip", "detail": f"{condition} already set in chain config"})
            continue
        pinned = "v_100" if slot == "governance/agent" and chain_settings.rollup_type in AGENT_PIN else None
        action, detail = plan_step(slot, raw, pinned)
        steps.append({"slot": slot, "action": action, "detail": detail})
    return steps


def unknown_folders(chain_settings):
    """Folders the deployer touches that STEPS does not list - i.e. this plan is stale.

    A call site with a variable segment (relayer/<rollup_type>) extracts only its literal
    prefix, so a planned slot under that prefix counts as covering it.
    """
    planned = {slot.format(rollup_type=chain_settings.rollup_type) for slot, _ in STEPS}
    return {f for f in deployer_folders() if not any(p == f or p.startswith(f + "/") for p in planned)}


def dry_run(chain_config_file):
    """Print the plan. Returns the number of blocking problems."""
    from settings.config import get_chain_settings

    try:
        chain_settings = get_chain_settings(chain_config_file)
    except Exception as exc:  # noqa: BLE001 - pydantic's message is the useful part
        raise click.ClickException(f"{chain_config_file} is not a valid chain config:\n{exc}") from exc

    env = Path(chain_config_file).parent.name
    deployment = BASE_DIR / "deployments" / env / f"{chain_settings.file_name}.yaml"
    raw = yaml.safe_load(deployment.read_text(encoding="utf-8")) if deployment.exists() else {}

    click.echo(f"dry run  {chain_config_file}  chain_id {chain_settings.chain_id}  {chain_settings.rollup_type}")
    click.echo(f"deployment file: {rel(deployment)}" + ("" if raw else "  (none yet)"))
    click.echo("")

    steps = build_plan(chain_settings, raw or {})
    width = max(len(s["slot"]) for s in steps)
    for step in steps:
        click.echo(f"  {step['action']:<8} {step['slot']:<{width}}  {step['detail']}")

    counts = {a: sum(1 for s in steps if s["action"] == a) for a in ("deploy", "reuse", "skip", "BLOCKED")}
    click.echo("")
    click.echo(f"{counts['deploy']} to deploy, {counts['reuse']} reused, {counts['skip']} skipped")

    stale = unknown_folders(chain_settings)
    if stale:
        click.echo(f"\nplan is out of date - the deployer also touches: {', '.join(sorted(stale))}")
    if counts["BLOCKED"]:
        click.echo(f"\n{counts['BLOCKED']} step(s) cannot run - `deploy all` would stop here")
    return counts["BLOCKED"] + len(stale)
