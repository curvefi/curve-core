import click

from scripts.tests import test_commands
from settings.logger import setup_logger

setup_logger()


@click.group("commands")
def commands(): ...


if __name__ == "__main__":
    commands.add_command(test_commands)
    commands()
