from pathlib import Path

import boa

from scripts.deploy.constants import BROADCASTERS
from scripts.deploy.deployment_file import get_deployment_obj
from scripts.deploy.deployment_utils import deploy_contract, update_deployment_chain_config
from scripts.deploy.utils import get_relative_path
from scripts.logging_config import get_logger
from settings.config import BASE_DIR, settings
from settings.models import ChainConfig, RollupType

logger = get_logger()


def deploy_xgov(chain_settings: ChainConfig):

    rollup_type = chain_settings.rollup_type

    # for specific rollup types we shall deploy v_100 agent since it is
    # vyper 0.3.10:
    version_to_deploy = "v_000"  # just deploy latest version!
    if rollup_type in ["arb_orbit", "op_stack", "polygon_cdk"]:
        version_to_deploy = "v_100"

    agent_blueprint = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "governance", "agent"),
        as_blueprint=True,
        deploy_contract_version=version_to_deploy,
    )

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
        case RollupType.taiko:
            r_args = ()
        case RollupType.not_rollup:
            # Currently temporary admin, Verifier with LZ Blockhash provider s00n
            r_args = (str(boa.env.eoa),)  # messenger
        case _:
            raise NotImplementedError(f"{rollup_type} currently not supported")

    if rollup_type == RollupType.not_rollup:
        args = (
            agent_blueprint.address,
            *r_args,
        )
    else:
        args = (
            BROADCASTERS[rollup_type],
            agent_blueprint.address,
            *r_args,
        )

    relayer = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "governance", "relayer", chain_settings.rollup_type),
        *args,
    )
    update_deployment_chain_config(
        chain_settings,
        {
            "dao": {
                "emergency_admin": str(relayer.EMERGENCY_AGENT()),
                "ownership_admin": str(relayer.OWNERSHIP_AGENT()),
                "parameter_admin": str(relayer.PARAMETER_AGENT()),
            }
        },
    )

    return relayer.OWNERSHIP_AGENT(), relayer.PARAMETER_AGENT(), relayer.EMERGENCY_AGENT()


def deploy_dao_vault(chain_settings: ChainConfig, owner: str):
    vault = deploy_contract(chain_settings, Path(BASE_DIR, "contracts", "governance", "vault"), owner)
    update_deployment_chain_config(chain_settings, {"dao": {"vault": str(vault.address)}})
    return vault


def transfer_ownership(chain_settings):

    deployment_file = get_deployment_obj(chain_settings)
    deployment_config = deployment_file.get_deployment_config()
    if deployment_config is None:
        raise ValueError(f"Deployment config not found for {chain_settings.network_name}")

    deployments = deployment_file.get_deployed_contracts()
    owner = chain_settings.dao.ownership_admin

    # TODO: rewrite it as VVM Contract doesn't have _storage
    for deployment in deployments:

        deployment_name = get_relative_path(deployment.compiler_data.contract_name)
        deployment_address = deployment.address

        for attr in ("admin", "owner"):
            if hasattr(deployment._storage, attr):
                current_owner = getattr(deployment._storage, attr).get()
                if current_owner != owner:
                    logger.info(f"Current {deployment_name} ({deployment_address}) owner: {current_owner}")
                    deployment.set_owner(owner)
                    logger.info(f"Set {deployment_name} owner to {owner}.")
                break
