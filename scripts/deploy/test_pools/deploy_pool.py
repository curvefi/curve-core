from enum import StrEnum
from pathlib import Path

import boa

from settings.config import BASE_DIR, CryptoPoolPresets

from ..deployment_file import YamlDeploymentFile
from ..utils import fetch_latest_contract


class PoolType(StrEnum):
    twocryptoswap = "twocryptoswap"


def deploy_pool(chain: str, name: str, symbol: str, coins: list[str], pool_type: PoolType = PoolType.twocryptoswap):
    deployment_file_path = Path(BASE_DIR, "deployments", f"{chain}.yaml")
    deployment_file = YamlDeploymentFile(deployment_file_path)
    factory = deployment_file.get_contract_deployment(("contracts", "amm", pool_type.value, "factory")).get_contract()
    pool_address = factory.deploy_pool(name, symbol, coins, 0, *CryptoPoolPresets().model_dump().values())
    pool = boa.load_partial(
        fetch_latest_contract(Path(BASE_DIR, "contracts", "amm", pool_type.value, "implementation"))
    ).at(pool_address)
    return pool, factory.address
