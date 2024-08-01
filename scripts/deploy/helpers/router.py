from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR, Settings


def deploy_router(chain_settings: Settings, wrapped_native_token):
    return deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "helpers", "router"),
        wrapped_native_token,
    )
