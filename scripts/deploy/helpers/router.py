from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR, ChainConfig


def deploy_router(chain_settings: ChainConfig):
    return deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "helpers", "router"),
        chain_settings.wrapped_native_token,
    )
