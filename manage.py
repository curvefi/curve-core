import os
import sys
import click
import boa
from eth_account import Account

from scripts.deploy import deploy_commands
from scripts.tests import test_commands
from settings.config import settings


@click.group(name="commands", help="Deployment & test command suite.")
def cli() -> None:
    """Top-level CLI group."""
    pass


def _init_network() -> None:
    """Initialize Boa network environment based on settings."""
    provider = getattr(settings, "WEB3_PROVIDER_URL", None)
    if not provider:
        click.echo("ERROR: WEB3_PROVIDER_URL is not set.", err=True)
        sys.exit(1)

    if getattr(settings, "DEBUG", False):
        # Fork latest state for safe local testing
        boa.fork(provider, block_identifier="latest")
    else:
        boa.set_network_env(provider)
        # Prefer settings value; fall back to env var if needed
        priv_key = getattr(settings, "DEPLOYER_EOA_PRIVATE_KEY", "") or os.getenv("DEPLOYER_EOA_PRIVATE_KEY", "")
        if not priv_key:
            click.echo(
                "WARNING: DEPLOYER_EOA_PRIVATE_KEY is empty. Continuing without a deployer account.",
                err=True,
            )
            return
        boa.env.add_account(Account.from_key(priv_key))


# Register sub-commands
cli.add_command(deploy_commands)
cli.add_command(test_commands)


if __name__ == "__main__":
    try:
        _init_network()
        cli()
    except Exception as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)
