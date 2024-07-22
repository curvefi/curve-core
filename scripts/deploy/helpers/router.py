from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR


def deploy_router(chain_name: str, weth: str):
    return deploy_contract(
        chain_name,
        "helpers",
        Path(BASE_DIR, "contracts", "helpers", "router"),
        weth,
    )
