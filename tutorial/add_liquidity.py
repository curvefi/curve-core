from pathlib import Path

import boa
from eth_account import Account

from settings.config import BASE_DIR, settings

### This is arbitrum sepolia, tokens are bridged from ETH sepolia
boa.set_network_env(settings.WEB3_PROVIDER_URL)
account = Account.from_key(settings.DEPLOYER_EOA_PRIVATE_KEY)
boa.env.add_account(account)

# Test pool deployed, change address of deployed contract here
POOL_ADDRESS = "0xF93cB94D001fd7948958913090DaD23D345E01D7"

pool = boa.load_partial(
    Path(BASE_DIR, "contracts", "amm", "twocryptoswap", "implementation", "implementation_v_210.vy")
).at(POOL_ADDRESS)

token1_address = pool.coins(0)
token2_address = pool.coins(1)

token1 = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(token1_address)
token2 = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(token2_address)

AMOUNT = 100_000 * 10**18

assert token1.balanceOf(account.address) >= AMOUNT, "Not enough tokens to add"
assert token2.balanceOf(account.address) >= AMOUNT, "Not enough tokens to add"

token1.approve(POOL_ADDRESS, AMOUNT)
token2.approve(POOL_ADDRESS, AMOUNT)

pool.add_liquidity([AMOUNT, AMOUNT], 0)
