from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR, Settings


def deploy_stable_swap_meta_zap(chain_settings: Settings):
    return deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "helpers", "stable_swap_meta_zap"),
    )
