from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR


def deploy_deposit_and_stake_zap(chain_name: str):
    return deploy_contract(
        chain_name,
        Path(BASE_DIR, "contracts", "helpers", "deposit_and_stake_zap"),
    )
