from pathlib import Path

import boa
from boa.contracts.abi.abi_contract import ABIContract

from settings.config import BASE_DIR, settings


def check_if_contract_deployed(address: str) -> bool:
    if settings.DEBUG:
        return True

    code = boa.env._rpc.fetch("eth_getCode", [address, "latest"])
    return code is not None


def check_contract_version(contract: ABIContract, version: str, deployment_type: str) -> bool:
    if deployment_type == "blueprint":
        # Can't check for blueprint unless deploy from blueprint
        return True

    return contract.version() == version


def get_contract(contract_path: str, address: str) -> ABIContract:
    contract_path = BASE_DIR / Path(contract_path.lstrip("/"))
    return boa.load_partial(contract_path).at(address)


def check_contracts(contracts: dict[str, dict]):
    for contract in contracts.values():
        assert check_if_contract_deployed(contract["contract"].address) is True

    for contract in contracts.values():
        assert (
            check_contract_version(contract["contract"], contract["contract_version"], contract["deployment_type"])
            is True
        )
