import json
import os
from enum import StrEnum
from pathlib import Path

import boa
from boa.contracts.abi.abi_contract import ABIContract
from eth_utils import keccak

from scripts.deploy.deployment_file import get_deployment_obj
from scripts.deploy.presets import CryptoPoolPresets
from scripts.logging_config import get_logger
from settings.config import BASE_DIR, ChainConfig

from .constants import CREATE2_SALT, CREATE2DEPLOYER_ABI, CREATE2DEPLOYER_ADDRESS
from .deployment_file import YamlDeploymentFile
from .utils import (
    fetch_filename_from_version,
    fetch_latest_contract,
    get_relative_path,
    get_version_from_filename,
    version_a_gt_version_b,
)

logger = get_logger()


def dump_initial_chain_settings(chain_settings: ChainConfig):
    get_deployment_obj(chain_settings).dump_initial_chain_settings(chain_settings)


def update_deployment_chain_config(chain_settings: ChainConfig, data: dict):
    get_deployment_obj(chain_settings).update_deployment_config({"config": data})


def get_deployment_config(chain_settings: ChainConfig):
    return get_deployment_obj(chain_settings).get_deployment_config()


def deploy_contract(
    chain_settings: ChainConfig,
    contract_folder: Path,
    *args,
    as_blueprint: bool = False,
    deploy_contract_version: str = "v_000",
):
    deployment_file = get_deployment_obj(chain_settings)

    # ---------------------------------------------- FETCH CONTRACT ----------------------------------------------

    if deploy_contract_version is not "v_000":

        contract_to_deploy = fetch_filename_from_version(contract_folder, deploy_contract_version)

    else:

        # fetch latest contract
        latest_contract = fetch_latest_contract(contract_folder)
        version_latest_contract = get_version_from_filename(latest_contract)

        # check if it has been deployed already
        parts = contract_folder.parts
        yaml_keys = contract_folder.parts[parts.index("contracts") :]
        contract_designation = parts[-1]
        deployed_contract = deployment_file.get_contract_deployment(yaml_keys)

        # if deployed, fetch deployed version
        deployed_contract_version = "0.0.0"  # contract has never been deployed
        if deployed_contract:
            deployed_contract_version = deployed_contract.contract_version  # contract has been deployed

        # deploy contract if nothing has been deployed, or if deployed contract is old
        if version_a_gt_version_b(version_latest_contract, deployed_contract_version):

            logger.info(f"Deploying {os.path.basename(latest_contract)} version {version_latest_contract}")
            contract_to_deploy = latest_contract

        else:

            # return contract object of existing deployment
            logger.info(
                f"{contract_designation} contract already deployed at {deployed_contract.address}. Fetching ..."
            )
            return boa.load_partial(latest_contract).at(deployed_contract.address)

    # ---------------------------------------------------- DEPLOY ----------------------------------------------------

    if not as_blueprint:
        deployed_contract = boa.load_partial(contract_to_deploy).deploy(*args)
    else:
        deployed_contract = boa.load_partial(contract_to_deploy).deploy_as_blueprint(*args)

    # store abi
    relpath = get_relative_path(contract_folder / os.path.basename(contract_to_deploy))
    abi_path = str(relpath).replace("contracts", "abi").replace(".vy", ".json")
    abi_path = BASE_DIR / Path(*Path(abi_path).parts[1:])

    if not os.path.exists(abi_path.parent):
        os.makedirs(abi_path.parent)

    with open(abi_path, "w") as abi_file:
        json.dump(deployed_contract.abi, abi_file, indent=4)
        abi_file.write("\n")

    # update deployment yaml file
    deployment_file.update_contract_deployment(
        contract_folder,
        deployed_contract,
        args,
        as_blueprint=as_blueprint,
    )

    return deployed_contract


def deploy_via_create2(contract_file, abi_encoded_ctor="", is_blueprint=False):
    create2deployer = boa.loads_abi(CREATE2DEPLOYER_ABI).at(CREATE2DEPLOYER_ADDRESS)
    contract_obj = boa.load_partial(contract_file)
    compiled_bytecode = contract_obj.compiler_data.bytecode
    deployment_bytecode = compiled_bytecode + abi_encoded_ctor
    if is_blueprint:
        blueprint_preamble = b"\xFE\x71\x00"
        # Add blueprint preamble to disable calling the contract:
        blueprint_bytecode = blueprint_preamble + deployment_bytecode
        # Add code for blueprint deployment:
        len_blueprint_bytecode = len(blueprint_bytecode).to_bytes(2, "big")
        deployment_bytecode = b"\x61" + len_blueprint_bytecode + b"\x3d\x81\x60\x0a\x3d\x39\xf3" + blueprint_preamble

    precomputed_address = create2deployer.computeAddress(CREATE2_SALT, keccak(deployment_bytecode))
    create2deployer.deploy(0, CREATE2_SALT, deployment_bytecode)
    return contract_obj.at(precomputed_address)


class PoolType(StrEnum):
    twocryptoswap = "twocryptoswap"


def deploy_pool(
    chain: str, name: str, symbol: str, coins: list[str], pool_type: PoolType = PoolType.twocryptoswap
) -> None:
    deployment_file_path = Path(BASE_DIR, "deployments", f"{chain}.yaml")
    deployment_file = YamlDeploymentFile(deployment_file_path)
    factory = deployment_file.get_contract_deployment(("contracts", "amm", pool_type.value, "factory")).get_contract()
    factory.deploy_pool(name, symbol, coins, 0, *CryptoPoolPresets().model_dump().values())
