import logging
from pathlib import Path

from scripts.deploy.constants import BROADCASTERS
from scripts.deploy.deployment_utils import deploy_contract, update_deployment_chain_config
from settings.config import BASE_DIR, ChainConfig, RollupType

logger = logging.getLogger(__name__)


def deploy_xgov(chain_settings: ChainConfig):
    agent_blueprint = deploy_contract(
        chain_settings, Path(BASE_DIR, "contracts", "governance", "agent"), as_blueprint=True
    )
    rollup_type = chain_settings.rollup_type

    match rollup_type:
        case RollupType.op_stack:
            r_args = ("0x4200000000000000000000000000000000000007",)  # messenger
        case RollupType.polygon_cdk:
            r_args = (
                "0x2a3DD3EB832aF982ec71669E178424b10Dca2EDe",  # bridge
                0,  # origin network
            )
        case RollupType.arb_orbit:
            r_args = ("0x0000000000000000000000000000000000000064",)  # arbsys
        case _:
            raise NotImplementedError(f"{rollup_type} currently not supported")

    relayer = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "governance", "relayer", chain_settings.rollup_type),
        BROADCASTERS[rollup_type],
        agent_blueprint.address,
        *r_args,
    )
    update_deployment_chain_config(
        chain_settings,
        {
            "dao": {
                "emergency_admin": relayer._immutables.EMERGENCY_AGENT,
                "ownership_admin": relayer._immutables.OWNERSHIP_AGENT,
                "parameter_admin": relayer._immutables.PARAMETER_AGENT,
            }
        },
    )

    return relayer.OWNERSHIP_AGENT(), relayer.PARAMETER_AGENT(), relayer.EMERGENCY_AGENT()


def deploy_dao_vault(chain_settings: ChainConfig, owner: str):
    vault = deploy_contract(chain_settings, Path(BASE_DIR, "contracts", "governance", "vault"), owner)
    update_deployment_chain_config(chain_settings, {"dao": {"vault": str(vault.address)}})
    return vault
