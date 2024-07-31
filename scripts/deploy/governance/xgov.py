import logging
from pathlib import Path

import boa

from scripts.deploy.constants import ETHEREUM_ADMINS
from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR

logger = logging.getLogger(__name__)


def deploy_xgov(chain: str, rollup_type: str):
    agent_blueprint = deploy_contract(chain, Path(BASE_DIR, "contracts", "governance", "agent"), as_blueprint=True)

    if rollup_type == "optimism":
        b_args = (  # TODO: how to retrieve?
            "0x5E4e65926BA27467555EB562121fac00D24E9dD2",  # ovm_chain (Optimism Virtual Machine)
            "0x676A795fe6E43C17c668de16730c3F690FEB7120",  # ovm_messenger (L1CrossDomainMessengerProxy)
        )
        r_args = (
            "0x4200000000000000000000000000000000000007",  # messenger
        )
    elif rollup_type == "polygon_zkevm":
        b_args = (
            "0x2a3DD3EB832aF982ec71669E178424b10Dca2EDe",  # POLYGON_ZKEVM_BRIDGE
            3,  # destination network, TODO: how to retrieve?
        )
        r_args = (
            "0x2a3DD3EB832aF982ec71669E178424b10Dca2EDe",  # POLYGON_ZKEVM_BRIDGE
            0,  # origin network
        )
    elif rollup_type == "arbitrum":
        b_args = (  # TODO
            "0x4Dbd4fc535Ac27206064B68FfCf827b0A60BAB3f",  # arb_inbox
            "",  # arb_refund
        )
        r_args = (
            "0x000000000000000000000000000000000000064",  # arbsys
        )
    else:
        raise "RollupNotSupported"

    broadcaster = deploy_contract("ethereum", Path(BASE_DIR, "contracts", "governance", chain, "broadcaster"), ETHEREUM_ADMINS, *b_args)
    relayer = deploy_contract(chain, Path(BASE_DIR, "contracts", "governance", chain, "relayer"), broadcaster, agent_blueprint, *r_args)
    broadcaster.set_relayer(relayer)  # TODO chain = ethereum

    return relayer.OWNERSHIP_AGENT(), relayer.PARAMETER_AGENT(), relayer.EMERGENCY_AGENT()


def deploy_dao_vault(chain: str, owner: str):
    return deploy_contract(chain, Path(BASE_DIR, "contracts", "governance", "vault"), owner)
