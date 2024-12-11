from pathlib import Path

from scripts.deploy.deployment_utils import deploy_contract
from settings.config import BASE_DIR
from settings.models import ChainConfig


def deploy_deposit_and_stake_zap(chain_settings: ChainConfig):
    return deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "helpers", "deposit_and_stake_zap"),
    )
