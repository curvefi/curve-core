import logging
from pathlib import Path

import boa

from scripts.deploy.constants import ZERO_ADDRESS
from scripts.deploy.models import CurveDAONetworkSettings
from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR

logger = logging.getLogger(__name__)


def deploy_liquidity_gauge_infra(chain: str, network_settings: CurveDAONetworkSettings):

    # owner = network_settings.dao_ownership_contract
    owner = boa.env.eoa  # TODO: set correct owner!
    crv_token_address = network_settings.crv_token_address

    # we set the call proxy address and the root gauge implementation address to zero since these are not
    # immediately available to new chains and are specific for transferring CRV emissions from mainnet
    # to child chain. Since crv emissions will not be available in curve-lite from the getgo, these gauges
    # will function as reward-only gauges until the owner of the factory sets self.crv address, self.call_proxy
    # self.root_implementation, and gauges individually set self.root_gauge address
    call_proxy_address = ZERO_ADDRESS
    root_gauge_implementation_address = ZERO_ADDRESS
    root_factory_address = ZERO_ADDRESS

    # deploy gauge factory and gauge implementaiton address
    child_gauge_factory = deploy_contract(
        chain,
        Path(BASE_DIR, "contracts", "gauge", "child_gauge", "factory"),
        call_proxy_address,
        root_factory_address,
        root_gauge_implementation_address,
        owner,
    )
    child_gauge_implementation = deploy_contract(
        chain, Path(BASE_DIR, "contracts", "gauge", "child_gauge", "implementation"), child_gauge_factory.address
    )

    # set child gauge implementation on the child gauge factory
    child_gauge_factory.set_implementation(child_gauge_implementation.address)

    # TODO: if owner is dao, then the above step is not possible. refactor init ctor for this
