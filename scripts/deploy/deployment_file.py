import re
import time
from pathlib import Path

import yaml
from boa.contracts.abi.abi_contract import ABIFunction
from boa.contracts.vyper.vyper_contract import VyperContract
from boa.util.abi import abi_encode
from pydantic import BaseModel
from pydantic.v1.utils import deep_update

import scripts.deploy.models as DataModels
from scripts.logging_config import get_logger
from settings.config import BASE_DIR, settings
from settings.models import ChainConfig

from .utils import get_latest_commit_hash, get_relative_path

logger = get_logger()


class YamlDeploymentFile:

    def __init__(self, _file_path: Path):
        self.file_path = _file_path
        self.file_name = _file_path.stem

    def get_deployment_config(self) -> DataModels.DeploymentConfig | None:
        if not self.file_path.exists():
            return None
        with open(self.file_path, "r") as file:
            deployments = yaml.safe_load(file)

        return DataModels.DeploymentConfig.model_validate(deployments)

    def get_contract_deployment(self, config_keys: tuple) -> DataModels.Contract | None:
        """
        Get contract deployment from deployment file if exits

        Args:
        config_keys (list): A list of keys that define contract path
        Returns:
        Contract | None: Contract if exits
        """
        current_level = self.get_deployment_config()
        if current_level is None:
            return None

        for key in config_keys:
            if isinstance(current_level, dict):  # workaround for dict pydantic field
                if key in current_level:
                    current_level = current_level[key]
                else:
                    return None
                continue

            if getattr(current_level, key) is not None:
                current_level = getattr(current_level, key)
            else:
                return None
        return current_level

    def save_deployment_config(self, deployment: DataModels.DeploymentConfig) -> None:
        with open(self.file_path, "w") as file:
            yaml.safe_dump(deployment.model_dump(), file)

    def update_deployment_config(self, data: dict) -> None:
        """
        Update whole deployment

        Args:
        data (dict): Data of any size for updating deployment (should have same nested values)
        """
        deployment_config = self.get_deployment_config()
        if deployment_config is not None:
            updated_deployment_config = deep_update(deployment_config.model_dump(), data)
        else:
            updated_deployment_config = data

        # Validate data
        DataModels.DeploymentConfig.model_validate(updated_deployment_config)

        with open(self.file_path, "w") as file:
            yaml.safe_dump(updated_deployment_config, file)

    @staticmethod
    def ensure_nested_dict(d: dict, keys: tuple) -> dict:
        """
        Ensure that a nested dictionary contains the given keys.
        If the keys do not exist, create them.

        Args:
        d (dict): The dictionary to update.
        keys (list): A list of keys that define the nested structure.
        Returns:
        dict: The innermost dictionary that corresponds to the final key in the keys list.
        """
        for key in keys:
            if key not in d or d[key] is None:
                d[key] = {}
            d = d[key]
        return d

    def update_contract_deployment(
        self,
        contract_folder: Path,
        contract_object: VyperContract,
        ctor_args: tuple,
        as_blueprint: bool = False,
    ):
        deployment_config_dict = self.get_deployment_config().model_dump()
        contract_path_keys = contract_folder.parts[contract_folder.parts.index("contracts") :]

        # fill nested keys if they don't exist and return the innermost nest based on contract_folder:
        contract_deployment = self.ensure_nested_dict(deployment_config_dict, contract_path_keys)

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
        github_url = (
            f"https://github.com/curvefi/curve-lite/blob/{latest_git_commit_for_file}/"
            f"{'/'.join(contract_relative_path.parts[1:])}"
        )

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
        contract_deployment.update(
            {
                "deployment_type": "normal" if not as_blueprint else "blueprint",
                "contract_version": version,
                "contract_path": str(contract_relative_path),
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
        )

        self.save_deployment_config(DataModels.DeploymentConfig.model_validate(deployment_config_dict))

    def dump_initial_chain_settings(self, chain_settings: ChainConfig):
        update_parameters = {
            "config": {
                **chain_settings.model_dump(exclude_none=True),
            }
        }
        self.update_deployment_config(update_parameters)

    def get_deployed_contracts(self):
        contracts = self.get_deployment_config().contracts
        contract_info = []

        def process_contracts(obj, path):
            if isinstance(obj, DataModels.Contract):
                contract_info.append(obj.get_contract())
            elif isinstance(obj, BaseModel):
                for field_name, _ in obj.__fields__.items():
                    process_contracts(getattr(obj, field_name), f"{path}.{field_name}" if path else field_name)

        process_contracts(contracts, "")
        return contract_info


def get_deployment_obj(chain_settings: ChainConfig) -> YamlDeploymentFile:
    config_filepath: Path = Path(chain_settings.file_path)
    deployment_file: str = chain_settings.file_path
    if settings.DEBUG:
        deployment_file = f"debug/{config_filepath.stem}.yaml"
    deployment_file_path = Path(BASE_DIR, "deployments", deployment_file)
    return YamlDeploymentFile(deployment_file_path)
