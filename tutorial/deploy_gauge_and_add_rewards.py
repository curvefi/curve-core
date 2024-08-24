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
GAUGE_FACTORY = "0xB4c6A1e8A14e9Fe74c88b06275b747145DD41206"
TOKEN_ADDRESS = CRV = "0x50FB01Ee521b9D22cdcb713a505019f41b8BBFf4"

# to deploy deterministically, to be changed if needed
SALT = "0x0000000000000000000000000000000000000000000000000000000000000000"

gauge_factory = boa.load_partial(Path(BASE_DIR, "contracts", "gauge", "child_gauge", "factory", "factory_v_100.vy")).at(
    GAUGE_FACTORY
)

# <--------------------------- DEPLOY GAUGE --------------------------->
gauge_address = gauge_factory.deploy_gauge(LP_TOKEN_ADDRESS, bytes.fromhex(SALT[2:]))
### 0x8b8E9b2B6a28A8ad97787AF2E6d5fad2B477B29a
gauge_address = "0x8b8E9b2B6a28A8ad97787AF2E6d5fad2B477B29a"

gauge = boa.load_partial(
    Path(BASE_DIR, "contracts", "gauge", "child_gauge", "implementation", "implementation_v_020.vy")
).at(gauge_address)

# <--------------------------- ADD REWARD TOKEN TO GAUGE --------------------------->
# this will add TOKEN_ADDRESS as reward and account as manager for reward
reward_token = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(CRV)
AMOUNT = 10_000 * 10**18
assert reward_token.balanceOf(account.address) >= AMOUNT, "Not enough tokens to add"

gauge.add_reward(CRV, account.address)
reward_token.approve(gauge_address, AMOUNT)
gauge.deposit_reward_token(CRV, AMOUNT)

# <--------------------------- DEPOSIT LP TOKEN --------------------------->
# deposits LP token to gauge to start earning rewards
# any user with LP can depost
lp_token = boa.load_partial(
    Path(BASE_DIR, "contracts", "amm", "twocryptoswap", "implementation", "implementation_v_210.vy")
).at(POOL_ADDRESS)

AMOUNT = 10_000 * 10**18
assert lp_token.balanceOf(account.address) >= AMOUNT, "Not enough tokens to deposit"
lp_token.approve(gauge_address, AMOUNT)
gauge.deposit(AMOUNT)
