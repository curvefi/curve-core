import logging
from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR, ChainConfig

logger = logging.getLogger(__name__)


def deploy_metaregistry(chain_settings: ChainConfig, gauge_factory_address: str, gauge_type: int):
    return deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "registries", "metaregistry"),
        gauge_factory_address,
        gauge_type,
    )


def update_metaregistry(chain_settings, metaregistry, address_provider):

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

    metaregistry.add_registry_handler(stableswap_handler)
    metaregistry.add_registry_handler(tricrypto_handler)
    metaregistry.add_registry_handler(twocrypto_handler)

    logger.info("Updated Metaregistry.")

    return metaregistry
