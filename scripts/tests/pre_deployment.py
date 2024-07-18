import logging

import boa

from scripts.deployment.utils import CREATE2DEPLOYER_ADDRESS
from settings.config import settings

logger = logging.getLogger(__name__)


def test_chain_id():
    chain_id = boa.env._rpc.fetch("eth_chainId", [])
    logger.info("Chain id: %r", int(chain_id, 0))
    return True  # TODO: input chain ID must be checked here ...


def test_evm_version():
    capabilities = boa.env.capabilities.describe_capabilities()
    result = "PASSED"
    if capabilities != "cancun":
        result = "FAILED"

    logger.info("Chain version is %r... %s", capabilities, result)
    return (
        result == "PASSED"
    )  # TODO: check if chain has a certain minimum evm version: PARIS


def test_create2deployer_deployed():
    code = boa.env._rpc.fetch(
        "eth_getCode", [CREATE2DEPLOYER_ADDRESS, "latest"]
    )
    if code is None:
        logger.info("Chain doesn't have create2deployer... FAILED")
        return False
    logger.info("Chain has create2deployer... PASSED")
    return True


def test_multicall3_deployed():
    code = boa.env._rpc.fetch(
        "eth_getCode", ["0xcA11bde05977b3631167028862bE2a173976CA11", "latest"]
    )
    if code is None:
        logger.info("Chain doesn't have multicall... FAILED")
        return False

    logger.info("Chain has multicall... PASSED")
    return True


def test_pre_deploy():
    boa.set_network_env(settings.WEB3_PROVIDER_URL)

    logger.info("Running pre deploy tests...")

    test_chain_id()
    test_evm_version()
    test_create2deployer_deployed()
    test_multicall3_deployed()

    logger.info("Pre deploy tests are finished.")
