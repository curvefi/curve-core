import logging

import click

from scripts.tests.post_deploy import test_post_deploy
from scripts.tests.pre_deployment import test_pre_deploy
from settings.config import get_chain_settings

logger = logging.getLogger(__name__)


@click.group(name="test")
def test_commands():
    """Commands related to test"""
    pass


@test_commands.command("pre_deploy", short_help="run pre deploy tests")
@click.argument("chain", type=click.STRING)
def run_test_pre_deploy(chain: str):
    settings = get_chain_settings(chain)
    test_pre_deploy(settings.chain_id)


@test_commands.command("post_deploy", short_help="run post deploy tests")
@click.argument("chain", type=click.STRING)
def run_test_post_deploy(chain: str):
    test_post_deploy(chain)
