from pathlib import Path

import boa
from eth_account import Account

from settings.config import BASE_DIR, settings

### This is arbitrum sepolia, tokens are bridged from ETH sepolia
boa.set_network_env(settings.WEB3_PROVIDER_URL)
account = Account.from_key(settings.DEPLOYER_EOA_PRIVATE_KEY)
boa.env.add_account(account)

# Test pool deployed, change address of deployed contract here
POOL_ADDRESS = LP_TOKEN_ADDRESS = "0x8AAC9F7068d2942E4Be0b979D98e098D9C42075D"
GAUGE_FACTORY = "0xA0a2998810cfCa4e3Bc2bc20621000713027939d"
TOKEN_ADDRESS = crvUSD = "0x92fc3EfE9129675A6d1405519C38b3aDdE4E0ADe"

# Can be anything, used for address derivation
SALT = "0x" + '0' * (64 - len(TOKEN_ADDRESS[2:])) + TOKEN_ADDRESS[2:]
### 0x00000000000000000000000050FB01Ee521b9D22cdcb713a505019f41b8BBFf4

gauge_factory = boa.load_partial(Path(BASE_DIR, "contracts", "gauge", "child_gauge", "factory", "factory_v_201.vy")).at(
    GAUGE_FACTORY
)

# <--------------------------- DEPLOY GAUGE --------------------------->
gauge_address = gauge_factory.deploy_gauge(LP_TOKEN_ADDRESS, bytes.fromhex(SALT[2:]))
gauge_address = "0x561b6B55CD02f9A91aD6474CBE0aa41169871901"

gauge = boa.load_partial(
    Path(BASE_DIR, "contracts", "gauge", "child_gauge", "implementation", "implementation_v_100.vy")
).at(gauge_address)

# <--------------------------- ADD REWARD TOKEN TO GAUGE --------------------------->
# this will add TOKEN_ADDRESS as reward and account as manager for reward
reward_token = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(crvUSD)
AMOUNT = 10_000 * 10**18
assert reward_token.balanceOf(account.address) >= AMOUNT, "Not enough tokens to add"

gauge.add_reward(crvUSD, account.address)
reward_token.approve(gauge_address, AMOUNT)
gauge.deposit_reward_token(crvUSD, AMOUNT)

# <--------------------------- DEPOSIT LP TOKEN --------------------------->
# deposits LP token to gauge to start earning rewards
# any user with LP can deposit
lp_token = boa.load_partial(
    Path(BASE_DIR, "contracts", "amm", "twocryptoswap", "implementation", "implementation_v_210.vy")
).at(POOL_ADDRESS)

AMOUNT = 10_000 * 10**18
assert lp_token.balanceOf(account.address) >= AMOUNT, "Not enough tokens to deposit"
lp_token.approve(gauge_address, AMOUNT)
gauge.deposit(AMOUNT)
