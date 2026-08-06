"""
Generated, consumable views of the deployment registry.

    python manage.py index           # write deployments/index.json and schema.json
    python manage.py index --check   # fail if either is stale (CI)

`deployments/` is the only cross-chain Curve address registry, but consuming it means
walking directories or enumerating them through the GitHub API - which needs a token.
These two files remove that: one HTTP GET of a raw file gets every chain and address,
and the schema says what a deployment file is allowed to contain.

Both are generated, never hand-edited, and `--check` in CI keeps them honest.
"""

import json

import click
import yaml

from scripts.deploy.models import DeploymentConfig
from scripts.status import contract_rows, rel
from settings.config import BASE_DIR

# Deliberately not inside deployments/: that directory holds nothing but chain folders, and
# consumers enumerate it. Adding files there would change what listing it returns.
INDEX_PATH = BASE_DIR / "registry" / "index.json"
SCHEMA_PATH = BASE_DIR / "registry" / "schema.json"

# Config keys worth publishing: identity, how to reach the chain, and how to render it.
# Deliberately not the whole config - `dao` and `reference_token_addresses` are nested and
# belong to the file itself, which the index points at.
CONFIG_KEYS = (
    "network_name",
    "chain_id",
    "layer",
    "is_testnet",
    "rollup_type",
    "native_currency_symbol",
    "native_currency_coingecko_id",
    "explorer_base_url",
    "public_rpc_url",
    "wrapped_native_token",
    "multicall3",
)


def contract_addresses(raw):
    """Every slot with a non-empty address, flattened to "amm.stableswap.factory" keys.

    Reuses status's walker rather than repeating it, so the index cannot come to see a
    different set of slots than the checks do - and inherits its one hard-won property:
    it keeps descending past a node that has an address of its own.
    """
    for slot, row in contract_rows(raw):
        if row.get("address"):
            yield slot, row["address"]


def build_index():
    """Every deployment file, flattened. Raises on a file that does not parse rather than
    quietly shipping an index that is missing a chain."""
    chains = []
    for path in sorted((BASE_DIR / "deployments").rglob("*.yaml")):
        if {"debug", "examples"} & set(path.parts):
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise click.ClickException(f"{path.relative_to(BASE_DIR).as_posix()} is not valid YAML: {exc}")
        config = raw.get("config") or {}
        entry = {
            "id": f"{path.parent.name}/{path.stem}",
            "file_name": config.get("file_name") or path.stem,
            "file_path": path.relative_to(BASE_DIR / "deployments").as_posix(),
            **{key: config.get(key) for key in CONFIG_KEYS},
            "contracts": dict(sorted(contract_addresses(raw))),
        }
        chains.append(entry)
    return {"count": len(chains), "chains": chains}


def render(data):
    """Byte-stable so --check compares content, not formatting."""
    return json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


@click.command("index", short_help="generate the registry index and JSON Schema")
@click.option("--check", is_flag=True, help="fail if the generated files are out of date")
def index_command(check):
    """Write deployments/index.json and deployments/schema.json."""
    wanted = {
        INDEX_PATH: render(build_index()),
        SCHEMA_PATH: render(DeploymentConfig.model_json_schema()),
    }
    stale = [p for p, text in wanted.items() if not p.exists() or p.read_text(encoding="utf-8") != text]

    if check:
        if stale:
            names = ", ".join(rel(p) for p in stale)
            raise click.ClickException(f"out of date: {names}\nRun `python manage.py index` and commit the result.")
        click.echo("index and schema are up to date")
        return

    for path, text in wanted.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    index = json.loads(wanted[INDEX_PATH])
    click.echo(f"wrote {index['count']} chains to {rel(INDEX_PATH)}")
    click.echo(f"wrote schema to {rel(SCHEMA_PATH)}")
