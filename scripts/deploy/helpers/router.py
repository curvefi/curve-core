from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR


def deploy_router(chain_name: str, native_wrapped_token: str):
    return deploy_contract(
        chain_name,
        Path(BASE_DIR, "contracts", "helpers", "router"),
        native_wrapped_token,
    )
