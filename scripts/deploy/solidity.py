from pathlib import Path

import boa
import solcx
from boa.contracts.abi.abi_contract import ABIContract, ABIContractFactory
from eth_abi import encode

# Solidity contracts are compiled with fixed settings, so bytecode doesn't depend on chain config.
# NOTE: solc 0.8.18 doesn't support evm versions after paris
SOLC_VERSION = "0.8.18"
SOLC_EVM_VERSION = "paris"
SOLC_OPTIMIZER_RUNS = 200


class SolidityDeployer:
    """Minimal counterpart of boa's Vyper deployer for Solidity contracts"""

    def __init__(self, abi: list[dict], bytecode: bytes, name: str, filename: str):
        self.abi = abi
        self.bytecode = bytecode
        self.factory = ABIContractFactory.from_abi_dict(abi, name=name, filename=filename)

    def deploy(self, *args) -> ABIContract:
        ctor = next((entry for entry in self.abi if entry["type"] == "constructor"), None)
        ctor_types = [arg["type"] for arg in ctor["inputs"]] if ctor else []
        if len(args) != len(ctor_types):
            raise ValueError(f"Expected {len(ctor_types)} constructor arguments, got {len(args)}")

        address, _ = boa.env.deploy_code(bytecode=self.bytecode + encode(ctor_types, args))
        return self.at(address)

    def at(self, address: str) -> ABIContract:
        return self.factory.at(address)


def load_partial_solidity(contract_path: Path, contract_name: str) -> SolidityDeployer:
    if SOLC_VERSION not in map(str, solcx.get_installed_solc_versions()):
        solcx.install_solc(SOLC_VERSION)

    compiled = solcx.compile_files(
        [contract_path],
        output_values=["abi", "bin"],
        solc_version=SOLC_VERSION,
        evm_version=SOLC_EVM_VERSION,
        optimize=True,
        optimize_runs=SOLC_OPTIMIZER_RUNS,
    )
    # keys are "{path}:{contract name}", libraries are compiled along
    contract = next(data for key, data in compiled.items() if key.rsplit(":", 1)[-1] == contract_name)
    return SolidityDeployer(contract["abi"], bytes.fromhex(contract["bin"]), contract_name, str(contract_path))
