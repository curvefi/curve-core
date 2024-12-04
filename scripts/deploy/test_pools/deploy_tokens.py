import logging
from pathlib import Path

import boa

from settings.config import BASE_DIR

logger = logging.getLogger(__name__)


def deploy_tokens() -> tuple:
    crv = boa.load(
        Path(BASE_DIR, "scripts", "deploy", "test_pools", "contracts", "ERC20mock.vy"),
        "Test Curve Token",
        "TEST_CRV",
        18,
    )
    crvusd = boa.load(
        Path(BASE_DIR, "scripts", "deploy", "test_pools", "contracts", "ERC20mock.vy"),
        "Test CrvUSD Token",
        "TEST_CRVUSD",
        18,
    )

    logger.info(f"CRV deployed at {crv.address}")
    logger.info(f"CRVUSD deployed at {crvusd.address}")

    crv._mint_for_testing(boa.env.eoa, 1_000_000 * 10**18)
    crvusd._mint_for_testing(boa.env.eoa, 1_000_000 * 10**18)

    return crv, crvusd
