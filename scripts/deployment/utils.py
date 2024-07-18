import os
import re
import subprocess

import boa
import yaml
from eth_utils import keccak

from scripts.deployment.constants import (
    CREATE2_SALT,
    CREATE2DEPLOYER_ABI,
    CREATE2DEPLOYER_ADDRESS,
)


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


def fetch_version(
    contract_designation, folder_path="contracts/helpers/router"
):
    # Regex pattern to match version numbers in filenames
    pattern = re.compile(rf"{contract_designation}_v_(\d+).vy")

    # List all files in the directory
    files = os.listdir(folder_path)

    # Filter and sort files by version number
    versions = []
    for file in files:
        match = pattern.match(file)
        if match:
            version = int(match.group(1))
            versions.append((version, file))

    if not versions:
        raise FileNotFoundError(
            f"No versions found for contract {contract_designation}"
        )

    # Get the file with the highest version number
    latest_version = max(versions, key=lambda x: x[0])

    return os.path.join(folder_path, latest_version[1])


def get_deployment(contract_designation, deployment_file):
    if not os.path.exists(deployment_file):
        return ""

    with open(deployment_file, "r") as file:
        deployments = yaml.safe_load(file)

    if contract_designation in deployments.keys():
        return deployments[contract_designation]

    return {}


def add_deployment(contract_designation, contract_object, deployment_file):
    if not os.path.exists(deployment_file):
        deployments = {}
    else:
        with open(deployment_file, "r") as file:
            deployments = yaml.safe_load(file)

    deployments[contract_designation] = {
        "version": contract_object.version().strip(),
        "contract_file": contract_object.filename,
        "latest_git_commit_hash": get_latest_commit_hash(
            contract_object.filename
        ),
        "address": contract_object.address.strip(),
    }

    with open(deployment_file, "w") as file:
        yaml.dump(deployments, file)


def deploy_via_create2(contract_file, abi_encoded_ctor="", is_blueprint=False):
    create2deployer = boa.loads_abi(CREATE2DEPLOYER_ABI).at(
        CREATE2DEPLOYER_ADDRESS
    )
    contract_obj = boa.load_partial(contract_file)
    compiled_bytecode = contract_obj.compiler_data.bytecode
    deployment_bytecode = compiled_bytecode + abi_encoded_ctor
    if is_blueprint:
        blueprint_preamble = b"\xFE\x71\x00"
        # Add blueprint preamble to disable calling the contract:
        blueprint_bytecode = blueprint_preamble + deployment_bytecode
        # Add code for blueprint deployment:
        len_blueprint_bytecode = len(blueprint_bytecode).to_bytes(2, "big")
        deployment_bytecode = (
            b"\x61"
            + len_blueprint_bytecode
            + b"\x3d\x81\x60\x0a\x3d\x39\xf3"
            + blueprint_preamble
        )

    precomputed_address = create2deployer.computeAddress(
        CREATE2_SALT, keccak(deployment_bytecode)
    )
    create2deployer.deploy(0, CREATE2_SALT, deployment_bytecode)
    return contract_obj.at(precomputed_address)
