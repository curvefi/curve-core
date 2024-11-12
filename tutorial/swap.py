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
VIEWS = "0xBB8e697BcDD4b68E904b5e332b9F07F35b8CE6B2"

pool = boa.load_partial(
    Path(BASE_DIR, "contracts", "amm", "twocryptoswap", "implementation", "implementation_v_210.vy")
).at(POOL_ADDRESS)
views = boa.load_partial(Path(BASE_DIR, "contracts", "amm", "twocryptoswap", "views", "views_v_200.vy")).at(VIEWS)

token1_address = pool.coins(0)
token2_address = pool.coins(1)

token1 = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(token1_address)
token2 = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(token2_address)

AMOUNT = 1_000 * 10**18

assert token1.balanceOf(account.address) >= AMOUNT, "Not enough tokens to add"

amount_out = views.get_dy(0, 1, AMOUNT, POOL_ADDRESS)

token1.approve(POOL_ADDRESS, AMOUNT)

pool.exchange(0, 1, AMOUNT, amount_out)
