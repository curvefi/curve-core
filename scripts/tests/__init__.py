import logging

import click

from scripts.tests.pre_deployment import test_pre_deploy

logger = logging.getLogger(__name__)


@click.group(name="test")
def test_commands():
    """Commands related to test"""
    pass


@test_commands.command("pre_deploy", short_help="run pre deploy tests")
def run_test_pre_deply():
    test_pre_deploy()
