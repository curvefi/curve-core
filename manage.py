import boa
import click
from eth_account import Account

from scripts.deploy import deploy_commands
from scripts.status import status_command
from scripts.tests import test_commands
from settings.config import settings

# Commands that talk to a chain. Everything else is read-only and skips the connection.
CHAIN_COMMANDS = ("deploy", "test")


@click.group("commands")
@click.pass_context
def commands(ctx):
    if ctx.invoked_subcommand not in CHAIN_COMMANDS:
        return

    if settings.DEBUG:
        boa.fork(settings.WEB3_PROVIDER_URL, block_identifier="latest")
    else:
        boa.set_network_env(settings.WEB3_PROVIDER_URL)
        boa.env.add_account(Account.from_key(settings.DEPLOYER_EOA_PRIVATE_KEY))


if __name__ == "__main__":
    commands.add_command(deploy_commands)
    commands.add_command(test_commands)
    commands.add_command(status_command)
    commands()
