import logging

import click

from scripts.deploy.helpers.deposit_and_stake_zap import deploy_deposit_and_stake_zap
from scripts.deploy.helpers.rate_provider import deploy_rate_provider
from scripts.deploy.helpers.stable_swap_meta_zap import deploy_stable_swap_meta_zap
from scripts.deploy.registries.metaregistry import deploy_metaregistry
from settings.config import RollupType, get_chain_settings

from .amm.stableswap import deploy_infra as deploy_stableswap
from .amm.tricrypto import deploy_infra as deploy_tricrypto
from .amm.twocrypto import deploy_infra as deploy_twocrypto
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

    # compile chain settings
    chain_settings = CurveNetworkSettings(
        dao_ownership_contract=settings.owner,
        fee_receiver_address=settings.fee_receiver,
        address_provider=address_provider.address,
        metaregistry=metaregistry.address,
    )

    # router
    router = deploy_router(chain, settings.weth)

    # deploy amms:
    stableswap_factory = deploy_stableswap(chain, chain_settings)
    tricrypto_factory = deploy_tricrypto(chain, chain_settings)
    twocrypto_factory = deploy_twocrypto(chain, chain_settings)

    # deposit and stake zap
    deposit_and_stake_zap = deploy_deposit_and_stake_zap(chain)

    # meta zap
    stable_swap_meta_zap = deploy_stable_swap_meta_zap(chain)

    # rate provider
    rate_provider = deploy_rate_provider(chain, chain_settings.address_provider)

    # add to the address provider:


@deploy_commands.command("router", short_help="deploy router")
@click.argument("chain", type=click.STRING)
def run_deploy_router(chain: str) -> None:
    settings = get_chain_settings(chain)
    deploy_router(chain, settings.weth)


@deploy_commands.command("address_provider", short_help="deploy address provider")
@click.argument("chain", type=click.STRING)
def run_deploy_address_provider(chain: str) -> None:
    deploy_address_provider(chain)


@deploy_commands.command("stableswap", short_help="deploy stableswap infra")
@click.argument("chain", type=click.STRING)
def run_deploy_stableswap(chain: str) -> None:
    settings = get_chain_settings(chain)
    chain_settings = CurveNetworkSettings(
        dao_ownership_contract=settings.owner, fee_receiver_address=settings.fee_receiver
    )
    deploy_stableswap(chain, chain_settings)


@deploy_commands.command("tricrypto", short_help="deploy tricrypto infra")
@click.argument("chain", type=click.STRING)
def run_deploy_tricrypto(chain: str) -> None:
    settings = get_chain_settings(chain)
    chain_settings = CurveNetworkSettings(
        dao_ownership_contract=settings.owner, fee_receiver_address=settings.fee_receiver
    )
    deploy_tricrypto(chain, chain_settings)


@deploy_commands.command("twocrypto", short_help="deploy twocrypto infra")
@click.argument("chain", type=click.STRING)
def run_deploy_twocrypto(chain: str) -> None:
    settings = get_chain_settings(chain)
    chain_settings = CurveNetworkSettings(
        dao_ownership_contract=settings.owner, fee_receiver_address=settings.fee_receiver
    )
    deploy_twocrypto(chain, chain_settings)
