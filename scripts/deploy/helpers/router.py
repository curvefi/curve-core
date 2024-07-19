from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR


def deploy_router(chain_name: str):
    deploy_contract(
        Path(BASE_DIR, "contracts", "helpers", "router"),
        chain_name,
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
    )
