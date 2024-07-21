import logging

import click

from scripts.command_options import chain, fee_receiver, owner, weth

from .amm.stableswap import deploy_infra as stableswap_deploy
from .helpers.router import deploy_router
from .models import CurveNetworkSettings
from .registries.address_provider import deploy_address_provider

logger = logging.getLogger(__name__)


@click.group(name="deploy")
def deploy_commands():
    """Commands related to deploy"""
    pass


@deploy_commands.command("all", short_help="deploy all to chain")
@chain
@owner
@fee_receiver
@weth
def run_deploy_all(chain: str, owner: str, fee_receiver: str, weth: str) -> None:
    logger.info("Deploying address provider at %r", chain)
    deploy_address_provider(chain)
    logger.info("Deployed address provider at %r", chain)
    logger.info("Deploying router at %r", chain)
    deploy_router(chain, weth)
    logger.info("Deployed router at %r", chain)

    chain_settings = CurveNetworkSettings(dao_ownership_contract=owner, fee_receiver_address=fee_receiver)

    logger.info("Deploying address provider at %r", chain)
    stableswap_deploy(chain, chain_settings)
    logger.info("Deployed address provider at %r", chain)


@deploy_commands.command("router", short_help="deploy router")
@chain
@weth
def run_deploy_router(chain: str, weth: str) -> None:
    logger.info("Deploying router at %r", chain)
    deploy_router(chain, weth)
    logger.info("Deployed router at %r", chain)


@deploy_commands.command("address_provider", short_help="deploy address provider")
@chain
def run_deploy_address_provider(chain: str) -> None:
    logger.info("Deploying address provider at %r", chain)
    deploy_address_provider(chain)
    logger.info("Deployed address provider at %r", chain)


@deploy_commands.command("stableswap", short_help="deploy stableswap infra")
@chain
@owner
@fee_receiver
def run_deploy_stableswap(chain: str, owner: str, fee_receiver: str) -> None:
    chain_settings = CurveNetworkSettings(dao_ownership_contract=owner, fee_receiver_address=fee_receiver)

    logger.info("Deploying stableswap at %r", chain)
    stableswap_deploy(chain, chain_settings)
    logger.info("Deployed stableswap at %r", chain)
