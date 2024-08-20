import logging

import click

from scripts.tests.post_deploy import test_post_deploy
from scripts.tests.pre_deployment import test_pre_deploy
from settings.config import RollupType, get_chain_settings

from .amm.stableswap import deploy_stableswap
from .amm.tricrypto import deploy_tricrypto
from .amm.twocrypto import deploy_twocrypto
from .constants import ADDRESS_PROVIDER_MAPPING, ZERO_ADDRESS
from .deployment_utils import deploy_pool, dump_initial_chain_settings
from .gauge.child_gauge import deploy_liquidity_gauge_infra
from .governance.xgov import deploy_dao_vault, deploy_xgov
from .helpers.deposit_and_stake_zap import deploy_deposit_and_stake_zap
from .helpers.rate_provider import deploy_rate_provider
from .helpers.router import deploy_router
from .helpers.stable_swap_meta_zap import deploy_stable_swap_meta_zap
from .registries.address_provider import deploy_address_provider
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
        admins = deploy_xgov(chain_settings)
        dao_vault = deploy_dao_vault(chain_settings, admins[0]).address

    # Old compatibility
    fee_receiver = dao_vault

    # deploy (reward-only) gauge factory and contracts
    child_gauge_factory = deploy_liquidity_gauge_infra(chain_settings)
    gauge_type = -1  # we set gauge type to -1 until there's an actual gauge type later
    # TODO: add post_deploy tests for gauge infra

    # address provider:
    address_provider = deploy_address_provider(chain_settings)

    # metaregistry:
    metaregistry = deploy_metaregistry(chain_settings, child_gauge_factory.address, gauge_type)

    # router
    router = deploy_router(chain_settings)

    # deploy amms:
    stableswap_factory = deploy_stableswap(chain_settings, fee_receiver)
    tricrypto_factory = deploy_tricrypto(chain_settings, fee_receiver)
    twocrypto_factory = deploy_twocrypto(chain_settings, fee_receiver)

    # deposit and stake zap
    deposit_and_stake_zap = deploy_deposit_and_stake_zap(chain_settings)

    # meta zap
    stable_swap_meta_zap = deploy_stable_swap_meta_zap(chain_settings)

    # rate provider
    rate_provider = deploy_rate_provider(chain_settings, address_provider.address)

    # add to the address provider:
    address_provider_inputs = {
        2: router.address,
        4: fee_receiver,
        7: metaregistry.address,
        11: tricrypto_factory.address,
        12: stableswap_factory.address,
        13: twocrypto_factory.address,
        18: rate_provider.address,
        20: child_gauge_factory.address,
        21: admins[0],
        22: admins[1],
        23: admins[2],
        24: dao_vault,
        26: deposit_and_stake_zap.address,
        27: stable_swap_meta_zap.address,
    }
    if chain_settings.dao and chain_settings.dao.crv:
        address_provider_inputs[19] = chain_settings.dao.crv
    if chain_settings.dao and chain_settings.dao.crvusd:
        address_provider_inputs[25] = chain_settings.dao.crvusd

    ids_to_add = []
    addresses_to_add = []
    descriptions_to_add = []

    ids_to_update = []
    for key, value in address_provider_inputs.items():

        # if id is empty:
        if not address_provider.check_id_exists(key):
            ids_to_add.append(key)
            addresses_to_add.append(value)
            descriptions_to_add.append(ADDRESS_PROVIDER_MAPPING[key])

        elif address_provider.get_address(key).strip().lower() != address_provider_inputs[key].strip().lower():
            ids_to_update.append(key)

    # add new ids to the address provider
    logger.info("Updating Address Provider.")
    if len(ids_to_add) > 0:
        address_provider.add_new_ids(ids_to_add, addresses_to_add, descriptions_to_add)

    # update existing ids
    if len(ids_to_update) > 0:
        for id in ids_to_update:
            logger.info(f"Updating ID {id} in the Address Provider.")
            address_provider.update_address(id, address_provider_inputs[id])

    # update metaregistry
    update_metaregistry(chain_settings, metaregistry, address_provider)

    # transfer ownership to the dao
    owner = admins[0]

    # addressprovider
    current_owner = address_provider._storage.admin.get()
    if not current_owner == owner:
        logger.info(f"Current address provider owner: {current_owner}")
        address_provider.set_owner(owner)
        logger.info(f"Set address provider owner to {owner}.")

    # metaregistry
    current_owner = metaregistry._storage.admin.get()
    if not current_owner == owner:
        logger.info(f"Current metaregistry owner: {current_owner}")
        metaregistry.set_owner(owner)
        logger.info(f"Set metaregistry owner to {owner}.")

    # gauge factory
    current_owner = child_gauge_factory._storage.owner.get()
    if not current_owner == owner:
        logger.info(f"Current liquidity child gauge factory owner: {current_owner}")
        child_gauge_factory.set_owner(owner)
        logger.info(f"Set liquidity child gauge factory owner to {owner}.")

    # stableswap
    current_owner = stableswap_factory._storage.admin.get()
    if not current_owner == owner:
        logger.info(f"Current stableswap factory owner: {current_owner}")
        stableswap_factory.set_owner(owner)
        logger.info(f"Set stableswap factory owner to {owner}.")

    # tricryptoswap
    current_owner = tricrypto_factory._storage.admin.get()
    if not current_owner == owner:
        logger.info(f"Current tricrypto factory owner: {current_owner}")
        tricrypto_factory.set_owner(owner)
        logger.info(f"Set tricrypto factory owner to {owner}.")

    # twocryptoswap
    current_owner = twocrypto_factory._storage.admin.get()
    if not current_owner == owner:
        logger.info(f"Current twocrypto factory owner: {current_owner}")
        twocrypto_factory.set_owner(owner)
        logger.info(f"Set twocrypto factory owner to {owner}.")

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
