from pathlib import Path

import boa

from scripts.deploy.constants import ZERO_ADDRESS
from scripts.deploy.deployment_utils import deploy_contract
from scripts.logging_config import get_logger
from settings.config import BASE_DIR, ChainConfig

logger = get_logger(__name__)


def deploy_metaregistry(chain_settings: ChainConfig, gauge_factory_address: str, gauge_type: int):
    return deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "registries", "metaregistry"),
        gauge_factory_address,
        gauge_type,
    )


def update_metaregistry(chain_settings: ChainConfig):
    address_provider = boa.load_partial(Path(BASE_DIR, "contracts", "registries", "address_provider")).at(
        chain_settings.deployments.registries.address_provider.address
    )

    metaregistry = boa.load_partial(Path(BASE_DIR, "contracts", "registries", "metaregistry")).at(
        chain_settings.deployments.registries.metaregistry.address
    )

    # deploy registry handlers
    stableswap_handler = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "registries", "metaregistry", "registry_handlers", "stableswap"),
        address_provider.get_address(12),  # stableswap factory is stored always on ID 12
    )
    tricrypto_handler = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "registries", "metaregistry", "registry_handlers", "tricryptoswap"),
        address_provider.get_address(11),
    )
    twocrypto_handler = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "registries", "metaregistry", "registry_handlers", "twocryptoswap"),
        address_provider.get_address(13),
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
