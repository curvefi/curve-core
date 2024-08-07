import logging
from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR, ChainConfig

logger = logging.getLogger(__name__)


def deploy_liquidity_gauge_infra(chain_settings: ChainConfig):

    # deploy gauge factory and gauge implementaiton address
    child_gauge_factory = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "gauge", "child_gauge", "factory"),
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

    logger.info("Liquidity Gauge Factory infra deployed.")

    return child_gauge_factory
