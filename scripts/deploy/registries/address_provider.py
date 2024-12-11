from pathlib import Path

import boa

from scripts.deploy.constants import AddressProviderID
from scripts.deploy.deployment_file import get_deployment_obj
from scripts.deploy.deployment_utils import deploy_contract
from scripts.logging_config import get_logger
from settings.config import BASE_DIR
from settings.models import ChainConfig

logger = get_logger()


def deploy_address_provider(chain_settings: ChainConfig):
    return deploy_contract(chain_settings, Path(BASE_DIR, "contracts", "registries", "address_provider"))


def update_address_provider(chain_settings: ChainConfig):

    deployment_config = get_deployment_obj(chain_settings).get_deployment_config()
    if deployment_config is None:
        raise ValueError(f"Deployment config not found for {chain_settings.network_name}")

    address_provider = deployment_config.contracts.registries.address_provider.get_contract()

    address_provider_inputs = {
        AddressProviderID.EXCHANGE_ROUTER.id: deployment_config.contracts.helpers.router.address,
        AddressProviderID.FEE_DISTRIBUTOR.id: chain_settings.dao.vault,  # Set fee receiver to dao vault
        AddressProviderID.METAREGISTRY.id: deployment_config.contracts.registries.metaregistry.address,
        AddressProviderID.TRICRYPTONG_FACTORY.id: deployment_config.contracts.amm.tricryptoswap.factory.address,
        AddressProviderID.STABLESWAPNG_FACTORY.id: deployment_config.contracts.amm.stableswap.factory.address,
        AddressProviderID.TWOCRYPTONG_FACTORY.id: deployment_config.contracts.amm.twocryptoswap.factory.address,
        AddressProviderID.SPOT_RATE_PROVIDER.id: deployment_config.contracts.helpers.rate_provider.address,
        AddressProviderID.GAUGE_FACTORY.id: deployment_config.contracts.gauge.child_gauge.factory.address,
        AddressProviderID.OWNERSHIP_ADMIN.id: chain_settings.dao.ownership_admin,
        AddressProviderID.PARAMETER_ADMIN.id: chain_settings.dao.parameter_admin,
        AddressProviderID.EMERGENCY_ADMIN.id: chain_settings.dao.emergency_admin,
        AddressProviderID.CURVEDAO_VAULT.id: chain_settings.dao.vault,
        AddressProviderID.DEPOSIT_AND_STAKE_ZAP.id: deployment_config.contracts.helpers.deposit_and_stake_zap.address,
        AddressProviderID.STABLESWAP_META_ZAP.id: deployment_config.contracts.helpers.stable_swap_meta_zap.address,
    }
    if chain_settings.dao and chain_settings.dao.crv:
        address_provider_inputs[AddressProviderID.CRV_TOKEN.id] = chain_settings.dao.crv
    if chain_settings.dao and chain_settings.dao.crvusd:
        address_provider_inputs[AddressProviderID.CRVUSD_TOKEN.id] = chain_settings.dao.crvusd

    ids_to_add = []
    addresses_to_add = []
    descriptions_to_add = []
    ids_to_update = []

    for key in AddressProviderID:
        if key.id in address_provider_inputs:
            if not address_provider.check_id_exists(key.id):
                ids_to_add.append(key.id)
                addresses_to_add.append(address_provider_inputs[key.id])
                descriptions_to_add.append(key.description)
            elif (
                address_provider.get_address(key.id).strip().lower() != address_provider_inputs[key.id].strip().lower()
            ):
                ids_to_update.append(key.id)

    logger.info("Updating Address Provider.")
    if ids_to_add:
        if address_provider.admin() != boa.env.eoa:
            logger.warning("Can not add new ideas, not admin anymore")
        else:
            address_provider.add_new_ids(ids_to_add, addresses_to_add, descriptions_to_add)

    for id in ids_to_update:
        logger.info(f"Updating ID {id} in the Address Provider.")
        if address_provider.admin() != boa.env.eoa:
            logger.warning("Could not update, not admin anymore")
        else:
            address_provider.update_address(id, address_provider_inputs[id])
