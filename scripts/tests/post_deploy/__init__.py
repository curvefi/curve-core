import logging
from pathlib import Path

import yaml

from settings.config import BASE_DIR

from .amm.stableswap import test_stableswap_deployment

logger = logging.getLogger(__name__)


def test_post_deploy(chain: str):
    """Test is run after whole infra is deployed"""

    logger.info("Starting post-deployment tests...")

    with open(Path(BASE_DIR, "deployments", f"{chain}.yaml"), "r") as file:
        deployments = yaml.safe_load(file)

    test_stableswap_deployment(deployments["contracts"]["amm"]["stableswap"])
    logger.info("Stableswap tests ... PASSED")

    logger.info("Post-deployment tests are finished.")
