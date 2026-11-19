from pathlib import Path

import boa

from scripts.deploy.constants import BLOCKHASH_ORACLE_CHAIN_IDS, BROADCASTERS, STORAGE_PROOF_ROLLUPS, get_relayer_type
from scripts.deploy.deployment_file import get_deployment_obj
from scripts.deploy.deployment_utils import deploy_contract, deploy_solidity_contract, update_deployment_chain_config
from scripts.deploy.utils import get_relative_path
from scripts.logging_config import get_logger
from settings.config import BASE_DIR
from settings.models import ChainConfig, RollupType

logger = get_logger()

OWNERSHIP_AGENT = 1  # Agent.OWNERSHIP in Relayer


def deploy_blockhash_oracle(chain_settings: ChainConfig):
    """Deploy oracle of Ethereum block hashes/state roots backed by rollup's native L1 feed"""
    rollup_type = chain_settings.rollup_type
    supported_chain_ids = BLOCKHASH_ORACLE_CHAIN_IDS.get(rollup_type)
    if supported_chain_ids is not None and chain_settings.chain_id not in supported_chain_ids:
        raise NotImplementedError(f"No {rollup_type} Block Hash Oracle for chain {chain_settings.chain_id}")

    blockhash_oracle = deploy_contract(
        chain_settings, Path(BASE_DIR, "contracts", "governance", "blockhash_oracle", rollup_type)
    )
    if rollup_type == RollupType.op_stack and blockhash_oracle.find_known_block_number() == 0:
        # L1Block predeploy keeps only the latest block, save one to check the feed is alive
        blockhash_oracle.apply()
        assert blockhash_oracle.find_known_block_number() > 0, "No L1 block in L1Block predeploy"
    return blockhash_oracle


def deploy_verifier(chain_settings: ChainConfig, blockhash_oracle, relayer):
    """Deploy storage proofs verifier of governance messages and set it as the only messenger of Relayer"""
    verifier = deploy_solidity_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "governance", "verifier"),
        "MessageDigestVerifier",
        blockhash_oracle.address,
        relayer.address,
    )
    assert verifier.BLOCK_HASH_ORACLE() == blockhash_oracle.address
    assert verifier.RELAYER() == relayer.address

    if relayer.messenger() != verifier.address:
        # Deployer is a temporary messenger, hand it over through Ownership Agent
        relayer.relay(OWNERSHIP_AGENT, [(relayer.address, relayer.set_messenger.prepare_calldata(verifier.address))])
    assert relayer.messenger() == verifier.address, "Verifier is not set as messenger"
    return verifier


def deploy_xgov(chain_settings: ChainConfig):

    rollup_type = chain_settings.rollup_type

    # for specific rollup types we shall deploy v_100 agent since it is
    # vyper 0.3.10:
    version_to_deploy = "v_000"  # just deploy latest version!
    if rollup_type in ["arb_orbit", "op_stack", "polygon_cdk"]:
        version_to_deploy = "v_100"

    # deploy oracle first, so unsupported chains fail before anything is deployed
    blockhash_oracle = None
    if rollup_type in STORAGE_PROOF_ROLLUPS:
        blockhash_oracle = deploy_blockhash_oracle(chain_settings)

    agent_blueprint = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "governance", "agent"),
        as_blueprint=True,
        deploy_contract_version=version_to_deploy,
    )

    match rollup_type:
        case RollupType.polygon_cdk:
            args = (
                BROADCASTERS[rollup_type],
                agent_blueprint.address,
                "0x2a3DD3EB832aF982ec71669E178424b10Dca2EDe",  # bridge
                0,  # origin network
            )
        case RollupType.arb_orbit:
            args = (
                BROADCASTERS[rollup_type],
                agent_blueprint.address,
                "0x0000000000000000000000000000000000000064",  # arbsys
            )
        case RollupType.op_stack | RollupType.taiko:
            # Deployer is a temporary messenger, replaced with Verifier below
            args = (agent_blueprint.address, str(boa.env.eoa))
        case RollupType.not_rollup:
            # Currently temporary admin, Verifier with LZ Blockhash provider s00n
            args = (agent_blueprint.address, str(boa.env.eoa))  # messenger
        case _:
            raise NotImplementedError(f"{rollup_type} currently not supported")

    relayer = deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "governance", "relayer", get_relayer_type(rollup_type)),
        *args,
    )
    if blockhash_oracle is not None:
        deploy_verifier(chain_settings, blockhash_oracle, relayer)

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

    for deployment in deployments:
        contract = deployment["contract"]
        is_blueprint = deployment["is_blueprint"]
        if is_blueprint:
            continue

        deployment_name = get_relative_path(contract.contract_name)
        deployment_address = contract.address

        for attr in ("admin", "owner"):
            if hasattr(contract, attr):
                current_owner = getattr(contract, attr)()
                if current_owner != owner:
                    logger.info(f"Current {deployment_name} ({deployment_address}) owner: {current_owner}")
                    contract.set_owner(owner)
                    logger.info(f"Set {deployment_name} owner to {owner}.")
                break
