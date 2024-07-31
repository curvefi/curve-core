import boa
from boa.contracts.abi.abi_contract import ABIContract

from settings.config import BASE_DIR, settings


def check_if_contract_deployed(address: str) -> bool:
    if settings.DEBUG:
        return True

    code = boa.env._rpc.fetch("eth_getCode", [address, "latest"])
    return code is not None


def get_relative_path(github_url: str) -> str:
    result = ""
    rel_path = False
    for el in str(github_url).split("/"):
        if el == "contracts":
            rel_path = True

        if rel_path:
            result += "/" + el

    return result


def get_contract(github_url: str, address: str) -> ABIContract:
    relative_path = get_relative_path(github_url)
    abi_path = relative_path.replace("/contracts/", "/abi/").replace(".vy", ".json")

    return boa.load_abi(str(BASE_DIR) + abi_path).at(address)


def check_contract_version(contract: ABIContract, version: str, deployment_type: str) -> bool:
    if deployment_type == "blueprint":
        # Can't check for blueprint unless deploy from blueprint
        return True

    return contract.version() == version


def check_contracts(contracts: dict[str, dict]):
    for contract in contracts.values():
        assert check_if_contract_deployed(contract["contract"].address) is True

    for contract in contracts.values():
        assert (
            check_contract_version(contract["contract"], contract["contract_version"], contract["deployment_type"])
            is True
        )
