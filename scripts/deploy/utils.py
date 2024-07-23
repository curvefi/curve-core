import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path

import boa
import yaml
from boa.contracts.abi.abi_contract import ABIFunction
from boa.contracts.vyper.vyper_contract import VyperContract
from boa.util.abi import abi_encode
from eth_utils import keccak
from pydantic_settings import BaseSettings

from settings.config import BASE_DIR, get_chain_settings

from .constants import CREATE2_SALT, CREATE2DEPLOYER_ABI, CREATE2DEPLOYER_ADDRESS

logger = logging.getLogger(__name__)


def deploy_contract(chain_name: str, category: str, contract_folder: Path, *args, as_blueprint: bool = False):

    deployment_file = Path(BASE_DIR, "deployments", f"{chain_name}.yaml")
    chain_settings = get_chain_settings(chain_name)

    # fetch latest contract
    latest_contract = fetch_latest_contract(contract_folder)
    version_latest_contract = get_version_from_filename(latest_contract)

    # check if it has been deployed already
    deployed_contract_dict = get_deployment(os.path.basename(contract_folder), deployment_file)

    deployed_contract_version = "0.0.0"  # contract has never been deployed
    if deployed_contract_dict:
        deployed_contract_version = deployed_contract_dict["version"]  # contract has been deployed

    # deploy contract if nothing has been deployed, or if deployed contract is old
    if version_a_gt_version_b(version_latest_contract, deployed_contract_version):

        # deploy contract
        if not as_blueprint:
            deployed_contract = boa.load_partial(latest_contract).deploy(*args)
        else:
            deployed_contract = boa.load_partial(latest_contract).deploy_as_blueprint(*args)

        # store abi
        relpath = get_relative_path(contract_folder)
        abi_path = relpath.replace("contracts", "abi")
        abi_file = f".{abi_path}/{os.path.basename(latest_contract).replace('.vy', '.json')}"

        if not os.path.exists(f".{abi_path}"):
            os.makedirs(f".{abi_path}")

        with open(abi_file, "w") as abi_file:
            json.dump(deployed_contract.abi, abi_file, indent=4)
            abi_file.write("\n")

        # update deployment yaml file
        save_deployment_metadata(
            category,
            os.path.basename(contract_folder),
            chain_settings,
            deployed_contract,
            deployment_file,
            args,
            as_blueprint=as_blueprint,
        )

    else:
        # return contract object of existing deployment
        deployed_contract = boa.load_partial(latest_contract).at(deployed_contract_dict["address"])

    return deployed_contract


def update_address_provider():

    pass


def get_latest_commit_hash(file_path):
    try:
        # Run the Git command to get the latest commit hash
        # for the specified file
        result = subprocess.run(
            ["git", "log", "-n", "1", "--pretty=format:%H", "--", file_path],
            capture_output=True,
            text=True,
            check=True,
        )
        # Return the commit hash
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error fetching commit hash: {e}")
        return None


def fetch_latest_contract(contract_folder: Path) -> Path:
    # Regex pattern to match version numbers in filenames
    contract_name = os.path.basename(contract_folder)
    pattern = re.compile(rf"{contract_name}_v_(\d+).vy")

    # Filter and sort files by version number
    versions = []
    for file in contract_folder.iterdir():
        match = pattern.match(os.path.basename(file))
        if match:
            version = int(match.group(1))
            versions.append((version, file))

    if not versions:
        raise FileNotFoundError(f"No versions found for contract {contract_name}")

    # Get the file with the highest version number
    latest_version = max(versions, key=lambda x: x[0])
    return latest_version[1]


def get_version_from_filename(filename: Path):
    # Extract the version part (e.g., v_110) from the filename
    version_str = os.path.basename(filename).split("_")[-1].split(".")[0]

    # Ensure the version string is in the correct format
    if len(version_str) == 3:
        major, minor, patch = version_str[0], version_str[1], version_str[2]
        return f"{major}.{minor}.{patch}"
    else:
        raise ValueError("Version string is not in the expected format")


def version_a_gt_version_b(a, b):
    return list(map(int, a.split("."))) > list(map(int, b.split(".")))


def get_deployment(contract_designation: str, deployment_file: Path):

    if not deployment_file.exists():
        return ""

    with open(deployment_file, "r") as file:
        deployments = yaml.safe_load(file)

    if contract_designation in deployments.keys():
        print(deployments["contracts"][contract_designation])
        breakpoint()
        return deployments["contracts"][contract_designation]

    return {}


def save_deployment_metadata(
    category: str,
    contract_designation: str,
    chain_settings: BaseSettings,
    contract_object: VyperContract,
    deployment_file: Path,
    ctor_args: list,
    as_blueprint: bool = False,
):
    if not os.path.exists(deployment_file):
        deployments = {"contracts": {category: {}}}
    else:
        with open(deployment_file, "r") as file:
            deployments = yaml.safe_load(file)
    if category not in deployments["contracts"]:
        deployments["contracts"][category] = {}

    # get abi-encoded ctor args:
    if ctor_args:
        ctor_abi_object = ABIFunction(
            next(i for i in contract_object.abi if i["type"] == "constructor"), contract_name="ctor_abi"
        )
        abi_args = ctor_abi_object._merge_kwargs(*ctor_args)
        encoded_args = abi_encode(ctor_abi_object.signature, abi_args).hex()
    else:
        encoded_args = None

    # fetch data from contract pragma:
    pattern = r"# pragma version ([\d.]+)"
    match = re.search(pattern, contract_object.compiler_data.source_code)
    if match:
        compiler_version = match.group(1)
    else:
        raise ValueError("Compiler Version is set incorrectly")

    # latest git commit hash:
    latest_git_commit_for_file = get_latest_commit_hash(contract_object.filename)
    contract_relative_path = get_relative_path(contract_object.filename)
    github_url = f"https://github.com/curvefi/curve-lite/blob/{latest_git_commit_for_file}{contract_relative_path}"

    if not as_blueprint:
        version = contract_object.version().strip()
    else:
        pattern = 'version: public\(constant\(String\[8\]\)\) = "([\d.]+)"'
        match = re.search(pattern, contract_object.compiler_data.source_code)

        if match:
            version = match.group(1)
        else:
            raise ValueError("Contract version is set incorrectly")

    # store contract deployment metadata:
    deployments["contracts"][category][contract_designation] = {
        "deployment_type": "normal" if not as_blueprint else "blueprint",
        "contract_version": version,
        "contract_github_url": github_url,
        "address": contract_object.address.strip(),
        "deployment_timestamp": int(time.time()),
        "constructor_args_encoded": encoded_args,
        "compiler_settings": {
            "compiler_version": compiler_version,
            "optimisation_level": contract_object.compiler_data.settings.optimize._name_,
            "evm_version": contract_object.compiler_data.settings.evm_version,
        },
    }
    deployments["config"] = {
        "chain": chain_settings.chain,
        "chain_id": chain_settings.chain_id,
        "chain_type": {
            "layer": chain_settings.layer,
            "rollup_type": chain_settings.rollup_type.value,
        },
        "weth": chain_settings.weth,
        "owner": chain_settings.owner,
        "fee_receiver": chain_settings.fee_receiver,
    }

    with open(deployment_file, "w") as file:
        yaml.dump(deployments, file)


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


def get_relative_path(contract_file: str) -> str:
    result = ""
    rel_path = False
    for el in str(contract_file).split("/"):
        if el == "contracts":
            rel_path = True

        if rel_path:
            result += "/" + el

    return result
