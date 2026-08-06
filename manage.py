import sys

import boa
import click
from eth_account import Account

from scripts.compare import compare_command
from scripts.deploy import deploy_commands
from scripts.index import index_command
from scripts.status import status_command
from scripts.tests import test_commands
from settings.config import settings

# Commands that do NOT touch a chain, listed as the exception so anything added later
# defaults to getting a connection rather than silently running without one.
READ_ONLY_COMMANDS = ("status", "compare", "index")


@click.group("commands")
@click.pass_context
def commands(ctx):
    if ctx.invoked_subcommand in READ_ONLY_COMMANDS:
        return

    # Asking what a command does should never open a connection or demand configuration.
    if "--help" in sys.argv or "-h" in sys.argv:
        return

    if not settings.WEB3_PROVIDER_URL:
        raise click.ClickException(
            "WEB3_PROVIDER_URL is not set. Put it in settings/env (see settings/env.example) "
            "or export it. Read-only commands such as `status` do not need it."
        )

    if settings.DEBUG:
        boa.fork(settings.WEB3_PROVIDER_URL, block_identifier="latest")
    else:
        if not settings.DEPLOYER_EOA_PRIVATE_KEY:
            raise click.ClickException(
                "DEPLOYER_EOA_PRIVATE_KEY is not set. Export it for the deploy only - "
                "do not store it in settings/env."
            )
        boa.set_network_env(settings.WEB3_PROVIDER_URL)
        boa.env.add_account(Account.from_key(settings.DEPLOYER_EOA_PRIVATE_KEY))


if __name__ == "__main__":
    commands.add_command(deploy_commands)
    commands.add_command(test_commands)
    commands.add_command(status_command)
    commands.add_command(compare_command)
    commands.add_command(index_command)
    commands()
