from pathlib import Path

import boa

from scripts.deploy.constants import ZERO_ADDRESS
from scripts.deploy.deployment_file import get_deployment_obj
from scripts.deploy.deployment_utils import deploy_contract
from scripts.logging_config import get_logger
from settings.config import BASE_DIR
from settings.models import ChainConfig

logger = get_logger()


def deploy_metaregistry(chain_settings: ChainConfig, gauge_factory_address: str, gauge_type: int):
    return deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "registries", "metaregistry"),
        gauge_factory_address,
        gauge_type,
    )


def update_metaregistry(chain_settings: ChainConfig):

    deployment_config = get_deployment_obj(chain_settings).get_deployment_config()
    if deployment_config is None:
        raise ValueError(f"Deployment config not found for {chain_settings.network_name}")

    metaregistry = deployment_config.contracts.registries.metaregistry.get_contract()

    # deploy registry handlers
    stableswap_handler = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "registries", "metaregistry", "registry_handlers", "stableswap"),
        deployment_config.contracts.amm.stableswap.factory.address,
    )
    tricrypto_handler = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "registries", "metaregistry", "registry_handlers", "tricryptoswap"),
        deployment_config.contracts.amm.tricryptoswap.factory.address,
    )
    twocrypto_handler = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "registries", "metaregistry", "registry_handlers", "twocryptoswap"),
        deployment_config.contracts.amm.twocryptoswap.factory.address,
    )

    logger.info("Adding registry handlers to the Metaregistry.")

    if metaregistry.get_registry(0) == ZERO_ADDRESS:
        metaregistry.add_registry_handler(stableswap_handler)
    if metaregistry.get_registry(1) == ZERO_ADDRESS:
        metaregistry.add_registry_handler(tricrypto_handler)
    if metaregistry.get_registry(2) == ZERO_ADDRESS:
        metaregistry.add_registry_handler(twocrypto_handler)

    logger.info("Updated Metaregistry.")

    return metaregistry
