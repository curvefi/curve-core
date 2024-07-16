import logging

import boa

from settings.config import settings

logger = logging.getLogger(__name__)


def test_chain_id():
    chain_id = boa.env._rpc.fetch("eth_chainId", [])
    logger.info("Chain id: %r", int(chain_id, 0))


def test_evm_version():
    capabilities = boa.env.capabilities.describe_capabilities()
    if capabilities != "cancun":
        logger.warning("Chain doesn't support cancun, version %r", capabilities)


def test_create2deployer_deployed():
    code = boa.env._rpc.fetch("eth_getCode", ["0x13b0D85CcB8bf860b6b79AF3029fCA081AE9beF2", "latest"])
    if code is None:
        logger.warning("Chain doesn't have create2deployer")


def test_multicall3_deployed():
    code = boa.env._rpc.fetch("eth_getCode", ["0xcA11bde05977b3631167028862bE2a173976CA11", "latest"])
    if code is None:
        logger.warning("Chain doesn't have multicall")


def test_pre_deploy():
    boa.set_network_env(settings.WEB3_PROVIDER_URL)

    logger.info("Running pre deploy tests...")

    test_chain_id()
    test_evm_version()
    test_create2deployer_deployed()
    test_multicall3_deployed()

    logger.info("Pre deploy tests are finished.")
