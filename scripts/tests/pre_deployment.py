import logging

import boa
from requests.exceptions import HTTPError

from scripts.deploy.constants import CREATE2DEPLOYER_ADDRESS, MULTICALL3_ADDRESS
from settings.config import settings

logger = logging.getLogger(__name__)


def test_chain_id(chain_id: int):
    chain_id_from_rpc = int(boa.env._rpc.fetch("eth_chainId", []), 0)
    logger.info("Chain id for RPC: %r", chain_id)
    assert chain_id_from_rpc == chain_id


def test_evm_version():
    try:
        capabilities = boa.env.capabilities.describe_capabilities()
        result = "PASSED"
        if capabilities != "cancun":
            result = "FAILED"

        logger.info("Chain version is %r... %s", capabilities, result)
        assert result == "PASSED"  # TODO: check if chain has a certain minimum evm version: PARIS
    except HTTPError:  # Some chains throw bad request for capabilities check
        pass


def test_create2deployer_deployed():
    code = boa.env._rpc.fetch("eth_getCode", [CREATE2DEPLOYER_ADDRESS, "latest"])
    if code is None:
        logger.info("Chain doesn't have create2deployer... FAILED")
    else:
        logger.info("Chain has create2deployer... PASSED")

    assert code is not None


def test_multicall3_deployed():
    code = boa.env._rpc.fetch("eth_getCode", [MULTICALL3_ADDRESS, "latest"])
    if code is None:
        logger.info("Chain doesn't have multicall... FAILED")
    else:
        logger.info("Chain has multicall... PASSED")

    assert code is not None


def test_pre_deploy(chain_id: int):

    if settings.DEBUG:
        logger.info("Skipping pre deployment tests in DEBUG mode...")
        return

    logger.info("Running pre deploy tests...")
    test_chain_id(chain_id)
    test_evm_version()
    test_create2deployer_deployed()
    test_multicall3_deployed()

    logger.info("Pre deploy tests are finished.")
