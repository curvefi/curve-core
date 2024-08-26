import logging
from pathlib import Path

import click

from scripts.tests.post_deploy import test_post_deploy
from scripts.tests.pre_deployment import test_pre_deploy
from settings.config import BASE_DIR, RollupType, get_chain_settings, settings

from .amm.stableswap import deploy_stableswap
from .amm.tricrypto import deploy_tricrypto
from .amm.twocrypto import deploy_twocrypto
from .deployment_utils import deploy_pool, dump_initial_chain_settings, get_deployment_config
from .gauge.child_gauge import deploy_liquidity_gauge_infra
from .governance.xgov import deploy_dao_vault, deploy_xgov, transfer_ownership
from .helpers.deposit_and_stake_zap import deploy_deposit_and_stake_zap
from .helpers.rate_provider import deploy_rate_provider
from .helpers.router import deploy_router
from .helpers.stable_swap_meta_zap import deploy_stable_swap_meta_zap
from .registries.address_provider import deploy_address_provider, update_address_provider
from .registries.metaregistry import deploy_metaregistry, update_metaregistry

logger = logging.getLogger(__name__)


@click.group(name="deploy")
def deploy_commands():
    """Commands related to deploy"""
    pass


@deploy_commands.command("all", short_help="deploy all to chain")
@click.argument("chain", type=click.STRING)
def run_deploy_all(chain: str) -> None:

    chain_settings = get_chain_settings(chain)
    if chain_settings.rollup_type == RollupType.zksync:
        raise NotImplementedError("zksync currently not supported")

    # If we are in debug mode, we want to remove the existing deployment file
    # so that there are no errors while trying to fetch state from a non-existent forked deployment
    if settings.DEBUG:
        deployment_file_path = Path(BASE_DIR, "deployments", f"{chain_settings.network_name}.yaml")
        if deployment_file_path.exists():
            logger.info(f"Removing existing deployment file {deployment_file_path} for debug deployment")
            deployment_file_path.unlink()

    # pre-deployment tests:
    test_pre_deploy(chain_settings.chain_id)

    # Save chain settings
    dump_initial_chain_settings(chain_settings)

    if chain_settings.rollup_type == RollupType.not_rollup:
        logger.info("No xgov for L1, setting temporary owner")
        admins = (
            chain_settings.dao.ownership_admin,
            chain_settings.dao.parameter_admin,
            chain_settings.dao.emergency_admin,
        )
        dao_vault = chain_settings.dao.vault
    else:
        # deploy xgov and dao vault
        admins = deploy_xgov(chain_settings)
        dao_vault = deploy_dao_vault(chain_settings, admins[0]).address

        # get updated chain settings from deployment file
        chain_settings = get_deployment_config(chain_settings).config

    # Old compatibility
    fee_receiver = dao_vault

    # deploy (reward-only) gauge factory and contracts
    child_gauge_factory = deploy_liquidity_gauge_infra(chain_settings)

    # address provider:
    address_provider = deploy_address_provider(chain_settings)

    # metaregistry
    gauge_type = -1  # we set gauge type to -1 until there's an actual gauge type later
    deploy_metaregistry(chain_settings, child_gauge_factory.address, gauge_type)

    # router
    deploy_router(chain_settings)

    # deploy amms:
    deploy_stableswap(chain_settings, fee_receiver)
    deploy_tricrypto(chain_settings, fee_receiver)
    deploy_twocrypto(chain_settings, fee_receiver)

    # deposit and stake zap
    deploy_deposit_and_stake_zap(chain_settings)

    # meta zap
    deploy_stable_swap_meta_zap(chain_settings)

    # rate provider
    deploy_rate_provider(chain_settings, address_provider.address)

    # update metaregistry
    update_metaregistry(chain_settings)

    # update address provider
    update_address_provider(chain_settings)

    # transfer ownership to the dao
    transfer_ownership(chain_settings)

    # test post deployment
    test_post_deploy(chain)

    # final!
    logger.info("Infra deployed and tested!")


@deploy_commands.command("governance", short_help="deploy governance")
@click.argument("chain", type=click.STRING)
def run_deploy_governance(chain: str) -> None:
    chain_settings = get_chain_settings(chain)
    admins = deploy_xgov(chain_settings)
    deploy_dao_vault(chain_settings, admins[0])


@deploy_commands.command("router", short_help="deploy router")
@click.argument("chain", type=click.STRING)
def run_deploy_router(chain: str) -> None:
    chain_settings = get_chain_settings(chain)
    deploy_router(chain_settings)


@deploy_commands.command("address_provider", short_help="deploy address provider")
@click.argument("chain", type=click.STRING)
def run_deploy_address_provider(chain: str) -> None:
    chain_settings = get_chain_settings(chain)
    deploy_address_provider(chain_settings)


@deploy_commands.command("stableswap", short_help="deploy stableswap infra")
@click.argument("chain", type=click.STRING)
@click.argument("fee_receiver", type=click.STRING)
def run_deploy_stableswap(chain: str, fee_receiver: str) -> None:
    chain_settings = get_chain_settings(chain)
    deploy_stableswap(chain_settings, fee_receiver)


@deploy_commands.command("tricrypto", short_help="deploy tricrypto infra")
@click.argument("chain", type=click.STRING)
@click.argument("fee_receiver", type=click.STRING)
def run_deploy_tricrypto(chain: str, fee_receiver: str) -> None:
    chain_settings = get_chain_settings(chain)
    deploy_tricrypto(chain_settings, fee_receiver)


@deploy_commands.command("twocrypto", short_help="deploy twocrypto infra")
@click.argument("chain", type=click.STRING)
@click.argument("fee_receiver", type=click.STRING)
def run_deploy_twocrypto(chain: str, fee_receiver: str) -> None:
    chain_settings = get_chain_settings(chain)
    deploy_twocrypto(chain_settings, fee_receiver)


@deploy_commands.command("crypto_pool", short_help="deploy twocrypto pool")
@click.argument("chain", type=click.STRING)
@click.argument("name", type=click.STRING)
@click.argument("symbol", type=click.STRING)
@click.argument("coins", type=click.STRING)
def run_deploy_twocrypto(chain: str, name: str, symbol: str, coins: str) -> None:
    deploy_pool(chain, name, symbol, coins.split(","))
