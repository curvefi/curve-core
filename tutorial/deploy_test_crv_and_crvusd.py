from pathlib import Path

import boa
from eth_account import Account

from settings.config import BASE_DIR, settings

### This is ETH(testnet) sepolia for mocking CRV and CRVUSD
boa.set_network_env(settings.WEB3_PROVIDER_URL)
boa.env.add_account(Account.from_key(settings.DEPLOYER_EOA_PRIVATE_KEY))


crv = boa.load(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy"), "Test Curve Token", "TEST_CRV", 18)
crvusd = boa.load(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy"), "Test CrvUSD Token", "TEST_CRVUSD", 18)

print(f"CRV deployed at {crv.address}")
print(f"CRVUSD deployed at {crvusd.address}")

#####
# ...
# CRV deployed at 0x6caAAdfD63E6c70E6c2A320153a620649fd8BF6e
# CRVUSD deployed at 0xC0e385097676445adD4313c322c96955549B3F10

crv._mint_for_testing(boa.env.eoa, 1_000_000 * 10**18)
crvusd._mint_for_testing(boa.env.eoa, 1_000_000 * 10**18)
