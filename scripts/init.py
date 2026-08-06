"""
Scaffold a chain config.

    python manage.py init prod/mychain
    python manage.py init devnet/mychain --rpc https://rpc.example.org

Onboarding a chain means writing settings/chains/{env}/{name}.yaml with twelve required
fields and no feedback until `deploy all` refuses to start. This asks for them, fills in
what the RPC can answer, and refuses to write a file that ChainConfig would reject.

Read-only with respect to chains: the only RPC calls are eth_chainId and eth_getCode.
"""

import textwrap
from pathlib import Path

import click
import yaml

from scripts.status import RpcError, _rpc_call, rel
from settings.config import BASE_DIR
from settings.models import ChainConfig, RollupType

CHAINS_DIR = BASE_DIR / "settings" / "chains"

# Same address on every chain that has it, which is why it is a default rather than a prompt.
# Whether this chain actually has it is a question only the chain can answer - see probe_chain.
MULTICALL3 = ChainConfig.model_fields["multicall3"].default


def probe_chain(rpc_url, timeout=15):
    """What the RPC can tell us: {"chain_id": int, "multicall3": bool}.

    Partial answers are useful, so a failed multicall3 probe is reported as unknown rather
    than sinking the whole scaffold.
    """
    result = {"chain_id": int(_rpc_call(rpc_url, "eth_chainId", [], timeout), 16)}
    try:
        code = _rpc_call(rpc_url, "eth_getCode", [MULTICALL3, "latest"], timeout)
        result["multicall3"] = bool(code) and code != "0x"
    except (OSError, RpcError, ValueError):
        result["multicall3"] = None
    return result


def render_config(answers):
    """YAML text, in the order the fields are usually read rather than alphabetically.

    Hand-written rather than yaml.safe_dump because the placeholders carry comments, and a
    template a newcomer cannot read is the problem this command exists to fix.
    """
    dao = answers.get("dao") or {}
    ref = answers.get("reference_token_addresses") or {}

    def quoted(value):
        return f'"{value}"' if value else ""

    def token(name):
        address = ref.get(name)
        return f"  {name}: {quoted(address)}" if address else f"  {name}:  # fill in for your chain"

    lines = [
        f"network_name: {answers['network_name']}",
        f"chain_id: {answers['chain_id']}",
        f"is_testnet: {answers['is_testnet']}",
        f"rollup_type: {answers['rollup_type']}",
    ]
    if dao:
        lines.append("dao:")
        lines += [f"  {key}: {quoted(value)}" for key, value in dao.items() if value]
    lines += [
        f"explorer_base_url: {answers['explorer_base_url']}",
        "",
        "# Not related to development, for further integrations",
        f"layer: {answers['layer']}",
        f"native_currency_symbol: {answers['native_currency_symbol']}",
        f"native_currency_coingecko_id: {answers['native_currency_coingecko_id']}",
        f"public_rpc_url: {answers['public_rpc_url']}",
        f"wrapped_native_token: {quoted(answers['wrapped_native_token'])}",
        f"logo_url: {answers['logo_url']}",
        "reference_token_addresses:",
        token("weth"),
        token("usdc"),
        token("usdt"),
    ]
    if answers.get("multicall3") and answers["multicall3"] != MULTICALL3:
        lines.append(f"multicall3: {quoted(answers['multicall3'])}")
    return "\n".join(lines) + "\n"


def validate_config(env, name, text):
    """ChainConfig's own verdict on the rendered text. Raises ValidationError.

    file_name and file_path are injected exactly as get_chain_settings() derives them from
    the path, so this is the same judgement `deploy all` will make.
    """
    data = yaml.safe_load(text) or {}
    return ChainConfig(**data, file_name=name, file_path=f"{env}/{name}.yaml")


def ask(answers, rpc_probe, rpc=None):
    """Fill in every required field, preferring what the chain itself reported."""
    answers["public_rpc_url"] = rpc or click.prompt("Public RPC url (used by the UI)")
    probed = {}
    try:
        probed = rpc_probe(answers["public_rpc_url"])
        click.echo(f"  chain_id from RPC: {probed['chain_id']}")
        if probed.get("multicall3") is False:
            click.echo(f"  warning: no multicall3 at {MULTICALL3} - the default will not work here")
    except Exception as exc:  # noqa: BLE001 - any RPC failure just means asking instead
        click.echo(f"  could not reach the RPC ({type(exc).__name__}), asking instead")

    answers["network_name"] = click.prompt("Network name")
    answers["chain_id"] = click.prompt("Chain id", type=int, default=probed.get("chain_id"))
    answers["is_testnet"] = click.confirm("Is this a testnet?", default=False)
    answers["layer"] = click.prompt("Layer", type=int, default=1)
    answers["rollup_type"] = click.prompt(
        "Rollup type", type=click.Choice([r.value for r in RollupType]), default=RollupType.not_rollup.value
    )
    answers["explorer_base_url"] = click.prompt("Explorer base url")
    answers["native_currency_symbol"] = click.prompt("Native currency symbol")
    answers["native_currency_coingecko_id"] = click.prompt("Native currency CoinGecko id (used for gas pricing)")
    answers["wrapped_native_token"] = click.prompt("Wrapped native token address")
    answers["logo_url"] = click.prompt("Logo url")
    answers["reference_token_addresses"] = {
        "weth": click.prompt("weth address", default="", show_default=False),
        "usdc": click.prompt("usdc address", default="", show_default=False),
        "usdt": click.prompt("usdt address", default="", show_default=False),
    }
    if probed.get("multicall3") is False:
        answers["multicall3"] = click.prompt("multicall3 address on this chain")
    return answers


@click.command("init", short_help="scaffold a chain config")
@click.argument("chain")
@click.option("--rpc", metavar="URL", default=None, help="probe this RPC instead of being asked for one")
@click.option("--force", is_flag=True, help="overwrite an existing config")
def init_command(chain, rpc, force):
    """Write settings/chains/CHAIN.yaml, where CHAIN is like prod/mychain."""
    if "/" not in chain:
        raise click.UsageError("CHAIN must include the directory, e.g. prod/mychain or devnet/mychain")
    env, _, name = chain.partition("/")
    name = Path(name).stem
    path = CHAINS_DIR / env / f"{name}.yaml"
    if path.exists() and not force:
        raise click.UsageError(f"{rel(path)} already exists - pass --force to overwrite")

    answers = ask({}, probe_chain, rpc)
    text = render_config(answers)
    try:
        validate_config(env, name, text)
    except Exception as exc:  # noqa: BLE001 - pydantic's message is the useful part
        raise click.ClickException(f"the answers do not make a valid config:\n{exc}") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    click.echo(f"\nwrote {rel(path)}")
    click.echo(
        textwrap.dedent(
            f"""
            Next:
              python manage.py status --chain {env}/{name}   # confirm nothing else is missing
              python manage.py deploy all {env}/{name}.yaml  # needs a funded deployer
            """
        ).strip()
    )
