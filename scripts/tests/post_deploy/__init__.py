import logging
from pathlib import Path

from scripts.deploy.deployment_file import YamlDeploymentFile
from settings.config import BASE_DIR, get_chain_settings

from .amm.stableswap import test_stableswap_deployment
from .amm.tricrypto import test_tricrypto_deployment
from .amm.twocrypto import test_twocrypto_deployment
from .gauge import test_gauge_deployment
from .helpers import test_helpers_deployment
from .registries import test_registries_deployment
from .xgov import test_xgov_deployment

logger = logging.getLogger(__name__)


def test_post_deploy(chain: str):
    """Test is run after whole infra is deployed"""

    logger.info("Starting post-deployment tests...")

    chain_settings = get_chain_settings(chain)
    deployment_file_path = Path(BASE_DIR, "deployments", f"{chain_settings.network_name}.yaml")
    deployment_file = YamlDeploymentFile(deployment_file_path)
    deployment = deployment_file.get_deployment_config()

    test_stableswap_deployment(deployment)
    logger.info("Stableswap tests ... PASSED")

    test_twocrypto_deployment(deployment)
    logger.info("Twocrypto tests ... PASSED")

    test_tricrypto_deployment(deployment)
    logger.info("Tricrypto tests ... PASSED")

    test_helpers_deployment(deployment)
    logger.info("Helpers tests ... PASSED")

    test_registries_deployment(deployment, chain_settings)
    logger.info("Registries tests ... PASSED")

    test_xgov_deployment(deployment)
    logger.info("Xgov tests ... PASSED")

    test_gauge_deployment(deployment)
    logger.info("Gauge tests ... PASSED")

    logger.info("Post-deployment tests are finished.")
