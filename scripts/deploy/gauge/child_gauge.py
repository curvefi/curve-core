from pathlib import Path

from scripts.deploy.constants import ROOT_GAUGE_FACTORY, ROOT_GAUGE_IMPLEMENTATION, ZERO_ADDRESS
from scripts.deploy.deployment_utils import deploy_contract
from scripts.logging_config import get_logger
from settings.config import BASE_DIR, ChainConfig

logger = get_logger(__name__)


def deploy_liquidity_gauge_infra(chain_settings: ChainConfig):

    # deploy gauge factory and gauge implementaiton address
    child_gauge_factory = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "gauge", "child_gauge", "factory"),
        ROOT_GAUGE_FACTORY,
        ROOT_GAUGE_IMPLEMENTATION,
        chain_settings.dao.crv or ZERO_ADDRESS,  # CRV
    )
    child_gauge_implementation = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "gauge", "child_gauge", "implementation"),
        child_gauge_factory.address,
    )

    # set child gauge implementation on the child gauge factory
    current_implementation = child_gauge_factory._storage.get_implementation.get()
    if not current_implementation == child_gauge_implementation.address:
        logger.info(f"Current liquidity child gauge implementation: {current_implementation}")
        child_gauge_factory.set_implementation(child_gauge_implementation.address)
        logger.info(f"Set liquidity child gauge implementation to {child_gauge_implementation.address}.")

    if chain_settings.dao and chain_settings.dao.crv:
        crv_address = child_gauge_factory._storage.crv.get()
        if crv_address != chain_settings.dao.crv:
            child_gauge_factory.set_crv(chain_settings.dao.crv)

    logger.info("Liquidity Gauge Factory infra deployed.")

    return child_gauge_factory
