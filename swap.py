from pathlib import Path

import boa
import argparse
from eth_account import Account

from settings.config import BASE_DIR, settings

boa.set_network_env(settings.WEB3_PROVIDER_URL)
account = Account.from_key(settings.DEPLOYER_EOA_PRIVATE_KEY)
boa.env.add_account(account)

parser = argparse.ArgumentParser(description="Swap tokens in a pool")
parser.add_argument("--pool_address", type=str, required=True, help="Address of the pool")
parser.add_argument("--views_address", type=str, required=True, help="Address of the views contract")
parser.add_argument("--amount_token_0", type=int, required=True, help="Amount of token 0 to swap")

args = parser.parse_args()

POOL_ADDRESS = args.pool_address
VIEWS = args.views_address
AMOUNT_TOKEN_0 = args.amount_token_0
pool = boa.load_partial(
    Path(BASE_DIR, "contracts", "amm", "twocryptoswap", "implementation", "implementation_v_210.vy")
).at(POOL_ADDRESS)
views = boa.load_partial(Path(BASE_DIR, "contracts", "amm", "twocryptoswap", "views", "views_v_200.vy")).at(VIEWS)

token0_address = pool.coins(0)
token1_address = pool.coins(1)

token0 = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(token0_address)
token1 = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(token1_address)

assert token0.balanceOf(account.address) >= AMOUNT_TOKEN_0, "Not enough tokens to add"

amount_out = views.get_dy(0, 1, AMOUNT_TOKEN_0, POOL_ADDRESS)

token0.approve(POOL_ADDRESS, AMOUNT_TOKEN_0)

pool.exchange(0, 1, AMOUNT_TOKEN_0, amount_out)
