from scripts.deploy.deployment_file import get_deployment_obj
from scripts.logging_config import get_logger
from settings.config import get_chain_settings

from .amm.stableswap import test_stableswap_deployment
from .amm.tricrypto import test_tricrypto_deployment
from .amm.twocrypto import test_twocrypto_deployment
from .gauge import test_gauge_deployment
from .helpers import test_helpers_deployment
from .registries import test_registries_deployment
from .xgov import test_xgov_deployment

logger = get_logger()


def test_post_deploy(chain_config_file: str, ignore_deployments: list[str]):
    """Test is run after whole infra is deployed"""

    logger.info("Starting post-deployment tests...")

    chain_settings = get_chain_settings(chain_config_file)
    deployment = get_deployment_obj(chain_settings).get_deployment_config()

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

    if "xgov" in ignore_deployments:
        logger.warning("Xgov tests ... IGNORED")
    else:
        test_xgov_deployment(deployment)
        logger.info("Xgov tests ... PASSED")

    test_gauge_deployment(deployment)
    logger.info("Gauge tests ... PASSED")

    logger.info("Post-deployment tests are finished.")
