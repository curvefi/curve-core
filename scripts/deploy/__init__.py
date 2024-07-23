import logging

import click

from scripts.deploy.registries.metaregistry import deploy_metaregistry
from settings.config import RollupType, get_chain_settings

from .amm.stableswap import deploy_infra as stableswap_deploy
from .amm.tricrypto import deploy_infra as tricrypto_deploy
from .amm.twocrypto import deploy_infra as twocrypto_deploy
from .constants import ZERO_ADDRESS
from .helpers.router import deploy_router
from .models import CurveNetworkSettings
from .registries.address_provider import deploy_address_provider

logger = logging.getLogger(__name__)


@click.group(name="deploy")
def deploy_commands():
    """Commands related to deploy"""
    pass


@deploy_commands.command("all", short_help="deploy all to chain")
@click.argument("chain", type=click.STRING)
def run_deploy_all(chain: str) -> None:

    settings = get_chain_settings(chain)

    if settings.rollup_type == RollupType.zksync:
        raise NotImplementedError("zksync currently not supported")

    # TODO: deploy dao ownership address

    # TODO: deploy dao owned vault

    # TODO: deploy (reward-only) gauge factory and contracts
    gauge_factory = ZERO_ADDRESS
    gauge_type = -1

    # NOTE: CRV token needed for gauge factory

    # deploy address provider:
    address_provider = deploy_address_provider(chain)

    # TODO: metaregistry needs gauge factory address
    metaregistry = deploy_metaregistry(chain, gauge_factory, gauge_type)

    chain_settings = CurveNetworkSettings(
        dao_ownership_contract=settings.owner,
        fee_receiver_address=settings.fee_receiver,
        address_provider=address_provider.address,
        metaregistry=metaregistry.address,
    )

    # router
    deploy_router(chain, settings.weth)

    # deploy amms:
    stableswap_deploy(chain, chain_settings)
    tricrypto_deploy(chain, chain_settings)
    twocrypto_deploy(chain, chain_settings)

    # deposit and stake zap

    # meta zap

    # rate provider


@deploy_commands.command("router", short_help="deploy router")
@click.argument("chain", type=click.STRING)
def run_deploy_router(chain: str) -> None:
    settings = get_chain_settings(chain)

    logger.info("Deploying router at %r", chain)
    deploy_router(chain, settings.weth)
    logger.info("Deployed router at %r", chain)


@deploy_commands.command("address_provider", short_help="deploy address provider")
@click.argument("chain", type=click.STRING)
def run_deploy_address_provider(chain: str) -> None:
    logger.info("Deploying address provider at %r", chain)
    deploy_address_provider(chain)
    logger.info("Deployed address provider at %r", chain)


@deploy_commands.command("stableswap", short_help="deploy stableswap infra")
@click.argument("chain", type=click.STRING)
def run_deploy_stableswap(chain: str) -> None:
    settings = get_chain_settings(chain)

    chain_settings = CurveNetworkSettings(
        dao_ownership_contract=settings.owner, fee_receiver_address=settings.fee_receiver
    )

    logger.info("Deploying stableswap at %r", chain)
    stableswap_deploy(chain, chain_settings)
    logger.info("Deployed stableswap at %r", chain)


@deploy_commands.command("tricrypto", short_help="deploy tricrypto infra")
@click.argument("chain", type=click.STRING)
def run_deploy_tricrypto(chain: str) -> None:
    settings = get_chain_settings(chain)

    chain_settings = CurveNetworkSettings(
        dao_ownership_contract=settings.owner, fee_receiver_address=settings.fee_receiver
    )

    logger.info("Deploying tricrypto at %r", chain)
    tricrypto_deploy(chain, chain_settings)
    logger.info("Deployed tricrypto at %r", chain)


@deploy_commands.command("twocrypto", short_help="deploy twocrypto infra")
@click.argument("chain", type=click.STRING)
def run_deploy_twocrypto(chain: str) -> None:
    settings = get_chain_settings(chain)

    chain_settings = CurveNetworkSettings(
        dao_ownership_contract=settings.owner, fee_receiver_address=settings.fee_receiver
    )

    logger.info("Deploying twocrypto at %r", chain)
    twocrypto_deploy(chain, chain_settings)
    logger.info("Deployed twocrypto at %r", chain)
