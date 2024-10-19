from pathlib import Path

import boa
from eth_account import Account

from settings.config import BASE_DIR, settings
import argparse

boa.set_network_env(settings.WEB3_PROVIDER_URL)
account = Account.from_key(settings.DEPLOYER_EOA_PRIVATE_KEY)
boa.env.add_account(account)

parser = argparse.ArgumentParser(description="Add liquidity to a pool")
parser.add_argument("--pool_address", type=str, required=True, help="Address of the pool")
parser.add_argument("--amount_token_0", type=float, required=True, help="Amount of token 0 to add")
parser.add_argument("--amount_token_1", type=float, required=True, help="Amount of token 1 to add")

args = parser.parse_args()

POOL_ADDRESS = args.pool_address
AMOUNT_TOKEN_0 = int(args.amount_token_0)
AMOUNT_TOKEN_1 = int(args.amount_token_1)

pool = boa.load_partial(
    Path(BASE_DIR, "contracts", "amm", "twocryptoswap", "implementation", "implementation_v_210.vy")
).at(POOL_ADDRESS)

token0_address = pool.coins(0)
token1_address = pool.coins(1)

token0 = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(token0_address)
token1 = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(token1_address)

assert token0.balanceOf(account.address) >= AMOUNT_TOKEN_0, "Not enough tokens to add"
assert token1.balanceOf(account.address) >= AMOUNT_TOKEN_1, "Not enough tokens to add"

token0.approve(POOL_ADDRESS, AMOUNT_TOKEN_0)
token1.approve(POOL_ADDRESS, AMOUNT_TOKEN_1)

pool.add_liquidity([AMOUNT_TOKEN_0, AMOUNT_TOKEN_1], 0)
