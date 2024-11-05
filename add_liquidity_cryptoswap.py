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

print(f"Token 0: {token0_address}")
print(f"Token 1: {token1_address}")

token0 = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(token0_address)
token1 = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(token1_address)

print(f"Token 0 balance: {token0.balanceOf(account.address)}")
print(f"Token 1 balance: {token1.balanceOf(account.address)}")

assert token0.balanceOf(account.address) >= AMOUNT_TOKEN_0, "Not enough tokens to add"
assert token1.balanceOf(account.address) >= AMOUNT_TOKEN_1, "Not enough tokens to add"

# Add debug prints for token details
print(f"\nToken 0 Details:")
print(f"Name: {token0.name()}")
print(f"Symbol: {token0.symbol()}")
print(f"Decimals: {token0.decimals()}")

print(f"\nToken 1 Details:")
print(f"Name: {token1.name()}")
print(f"Symbol: {token1.symbol()}")
print(f"Decimals: {token1.decimals()}")

# Add try-catch blocks around the critical operations
try:
    token0.approve(POOL_ADDRESS, AMOUNT_TOKEN_0)
    print(f"Successfully approved token0")
except Exception as e:
    print(f"Failed to approve token0: {str(e)}")
    exit(1)

try:
    token1.approve(POOL_ADDRESS, AMOUNT_TOKEN_1)
    print(f"Successfully approved token1")
except Exception as e:
    print(f"Failed to approve token1: {str(e)}")
    exit(1)

try:
    pool.add_liquidity([AMOUNT_TOKEN_0, AMOUNT_TOKEN_1], 0)
    print("Successfully added liquidity")
except Exception as e:
    print(f"Failed to add liquidity: {str(e)}")
    exit(1)
