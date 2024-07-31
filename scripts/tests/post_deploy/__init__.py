import logging
from pathlib import Path

import yaml

from settings.config import BASE_DIR, get_chain_settings

from .amm.stableswap import test_stableswap_deployment
from .amm.tricrypto import test_tricrypto_deployment
from .amm.twocrypto import test_twocrypto_deployment
from .helpers import test_helpers_deployment
from .registries import test_registries_deployment

logger = logging.getLogger(__name__)


def test_post_deploy(chain: str):
    """Test is run after whole infra is deployed"""

    logger.info("Starting post-deployment tests...")

    with open(Path(BASE_DIR, "deployments", f"{chain}.yaml"), "r") as file:
        deployments = yaml.safe_load(file)

    chain_settings = get_chain_settings(chain)

    test_stableswap_deployment(deployments["contracts"]["amm"]["stableswap"])
    logger.info("Stableswap tests ... PASSED")

    test_twocrypto_deployment(deployments["contracts"]["amm"]["twocryptoswap"])
    logger.info("Twocrypto tests ... PASSED")

    test_tricrypto_deployment(deployments["contracts"]["amm"]["tricryptoswap"])
    logger.info("Tricrypto tests ... PASSED")

    test_helpers_deployment(deployments["contracts"]["helpers"])
    logger.info("Helpers tests ... PASSED")

    test_registries_deployment(deployments["contracts"], chain_settings)
    logger.info("Registries tests ... PASSED")

    logger.info("Post-deployment tests are finished.")
