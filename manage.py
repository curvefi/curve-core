import click

from settings.logger import setup_logger
from tests import test_commands

setup_logger()


@click.group("commands")
def commands(): ...


if __name__ == "__main__":
    commands.add_command(test_commands)
    commands()
