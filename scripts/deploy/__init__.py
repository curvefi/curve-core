import logging

import click

from settings.config import RollupType, get_chain_settings

from .amm.stableswap import deploy_infra as deploy_stableswap
from .amm.tricrypto import deploy_infra as deploy_tricrypto
from .amm.twocrypto import deploy_infra as deploy_twocrypto
from .constants import ADDRESS_PROVIDER_MAPPING, ZERO_ADDRESS
from .governance.xgov import deploy_xgov, deploy_dao_vault
from .helpers.deposit_and_stake_zap import deploy_deposit_and_stake_zap
from .helpers.rate_provider import deploy_rate_provider
from .helpers.router import deploy_router
from .helpers.stable_swap_meta_zap import deploy_stable_swap_meta_zap
from .models import CurveDAONetworkSettings
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

    settings = get_chain_settings(chain)

    if settings.rollup_type == RollupType.zksync:
        raise NotImplementedError("zksync currently not supported")

    if settings.rollup_type == RollupType.not_rollup:
        logger.info("No xgov for L1, setting temporary owner")
        admins = (settings.owner, settings.owner, settings.owner)
        dao_vault = settings.owner
    else:
        admins = deploy_xgov(chain, settings.rollup_type)
        dao_vault = deploy_dao_vault(chain, admins[0])

    # TODO: deploy (reward-only) gauge factory and contracts
    gauge_factory = ZERO_ADDRESS
    gauge_type = -1

    # NOTE: dao assets needed
    crv_token = ZERO_ADDRESS
    crvusd_token = ZERO_ADDRESS

    # deploy address provider:
    address_provider = deploy_address_provider(chain)

    # TODO: metaregistry needs gauge factory address
    metaregistry = deploy_metaregistry(chain, gauge_factory, gauge_type)

    # compile chain settings
    curve_network_settings = CurveDAONetworkSettings(
        dao_ownership_contract=settings.owner,  # TODO: forward to owner later/set dao owner/add team agent
        dao_parameter_contract=admins[1],
        dao_emergency_contract=admins[2],
        dao_vault_contract=dao_vault,
        crv_token_address=crv_token,  # TODO: update with deployment
        crvusd_token_address=crvusd_token,  # TODO: update with deployment
        fee_receiver_address=settings.fee_receiver,
        address_provider_address=address_provider.address,
        metaregistry_address=metaregistry.address,
    )

    # router
    router = deploy_router(chain, settings.native_wrapped_token)

    # deploy amms:
    stableswap_factory = deploy_stableswap(chain, curve_network_settings)
    tricrypto_factory = deploy_tricrypto(chain, curve_network_settings)
    twocrypto_factory = deploy_twocrypto(chain, curve_network_settings)

    # deposit and stake zap
    deposit_and_stake_zap = deploy_deposit_and_stake_zap(chain)

    # meta zap
    stable_swap_meta_zap = deploy_stable_swap_meta_zap(chain)

    # rate provider
    rate_provider = deploy_rate_provider(chain, curve_network_settings.address_provider_address)

    # add to the address provider:
    address_provider_inputs = {
        2: router.address,
        4: curve_network_settings.fee_receiver_address,
        7: metaregistry.address,
        11: tricrypto_factory.address,
        12: stableswap_factory.address,
        13: twocrypto_factory.address,
        18: rate_provider.address,
        19: curve_network_settings.crv_token_address,  # TODO: update deployment
        20: gauge_factory,  # TODO: update deployment
        21: admins[0],
        22: admins[1],
        23: admins[2],
        24: dao_vault.address,
        25: curve_network_settings.crvusd_token_address,
        26: deposit_and_stake_zap.address,
        27: stable_swap_meta_zap.address,
    }

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
    update_metaregistry(chain, metaregistry, address_provider)

    # TODO: transfer ownership to dao

    # final!
    logger.info("Infra deployed!")


@deploy_commands.command("governance", short_help="deploy governance")
@click.argument("chain", type=click.STRING)
def run_deploy_governance(chain: str) -> None:
    settings = get_chain_settings(chain)
    admins = deploy_xgov(chain, settings.rollup_type)
    dao_vault = deploy_dao_vault(chain, admins[0])


@deploy_commands.command("router", short_help="deploy router")
@click.argument("chain", type=click.STRING)
def run_deploy_router(chain: str) -> None:
    settings = get_chain_settings(chain)
    deploy_router(chain, settings.native_wrapped_token)


@deploy_commands.command("address_provider", short_help="deploy address provider")
@click.argument("chain", type=click.STRING)
def run_deploy_address_provider(chain: str) -> None:
    deploy_address_provider(chain)


@deploy_commands.command("stableswap", short_help="deploy stableswap infra")
@click.argument("chain", type=click.STRING)
def run_deploy_stableswap(chain: str) -> None:
    settings = get_chain_settings(chain)
    chain_settings = CurveDAONetworkSettings(
        dao_ownership_contract=settings.owner, fee_receiver_address=settings.fee_receiver
    )
    deploy_stableswap(chain, chain_settings)


@deploy_commands.command("tricrypto", short_help="deploy tricrypto infra")
@click.argument("chain", type=click.STRING)
def run_deploy_tricrypto(chain: str) -> None:
    settings = get_chain_settings(chain)
    chain_settings = CurveDAONetworkSettings(
        dao_ownership_contract=settings.owner, fee_receiver_address=settings.fee_receiver
    )
    deploy_tricrypto(chain, chain_settings)


@deploy_commands.command("twocrypto", short_help="deploy twocrypto infra")
@click.argument("chain", type=click.STRING)
def run_deploy_twocrypto(chain: str) -> None:
    settings = get_chain_settings(chain)
    chain_settings = CurveDAONetworkSettings(
        dao_ownership_contract=settings.owner, fee_receiver_address=settings.fee_receiver
    )
    deploy_twocrypto(chain, chain_settings)
