from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR, Settings


def deploy_deposit_and_stake_zap(chain_settings: Settings):
    return deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "helpers", "deposit_and_stake_zap"),
    )
