from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR


def deploy_stable_swap_meta_zap(chain_name: str):
    return deploy_contract(
        chain_name,
        "helpers",
        Path(BASE_DIR, "contracts", "helpers", "stable_swap_meta_zap"),
    )
