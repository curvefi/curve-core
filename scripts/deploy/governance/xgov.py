import logging
from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR, ChainConfig, RollupType

logger = logging.getLogger(__name__)


BROADCASTERS = {
    RollupType.op_stack: "0xE0fE4416214e95F0C67Dc044AAf1E63d6972e0b9",
    RollupType.polygon_cdk: "0xB5e7fE8eA8ECbd33504485756fCabB5f5D29C051",
    RollupType.arb_orbit: "0x94630a56519c00Be339BBd8BD26f342Bf4bd7eE0",
}


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
        Path(BASE_DIR, "contracts", "governance", "relayer", chain_settings.rollup_type.value),
        BROADCASTERS[rollup_type],
        agent_blueprint.address,
        *r_args,
    )

    return relayer.OWNERSHIP_AGENT(), relayer.PARAMETER_AGENT(), relayer.EMERGENCY_AGENT()


def deploy_dao_vault(chain_settings: ChainConfig, owner: str):
    return deploy_contract(chain_settings, Path(BASE_DIR, "contracts", "governance", "vault"), owner)
