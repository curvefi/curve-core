import logging

import click

from .helpers.router import deploy_router

logger = logging.getLogger(__name__)


@click.group(name="deploy")
def deploy_commands():
    """Commands related to deploy"""
    pass


@deploy_commands.command("all", short_help="deploy all to chain")
@click.argument("chain_name", type=click.STRING)
def run_deploy_all(chain_name: str) -> None:
    deploy_router(chain_name)


@deploy_commands.command("router", short_help="deploy router")
@click.argument("chain_name", type=click.STRING)
@click.argument("weth", type=click.STRING)
def run_deploy_router(chain_name: str, weth: str) -> None:
    deploy_router(chain_name, weth)
