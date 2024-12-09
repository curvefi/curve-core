import logging

import boa
from boa.contracts.vyper.vyper_contract import VyperContract

logger = logging.getLogger(__name__)


def add_liquidity(pool: VyperContract, token0: VyperContract, token1: VyperContract, amount: int):
    assert token0.balanceOf(boa.env.eoa) >= amount, "Not enough tokens to add"
    assert token1.balanceOf(boa.env.eoa) >= amount, "Not enough tokens to add"

    token0.approve(pool.address, amount)
    token1.approve(pool.address, amount)

    pool.add_liquidity([amount, amount], 0)

    logger.info("Added liquidity")


def swap(pool: VyperContract, token0: VyperContract, amount: int):
    assert token0.balanceOf(boa.env.eoa) >= amount, "Not enough tokens to add"
    token0.approve(pool.address, amount)
    pool.exchange(0, 1, amount, 0)

    logger.info("Swapped tokens")
