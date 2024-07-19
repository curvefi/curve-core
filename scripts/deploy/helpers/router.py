from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR


def deploy_router(chain_name: str, WETH: str):
    return deploy_contract(
        Path(BASE_DIR, "contracts", "helpers", "router"),
        chain_name,
        WETH,
    )
