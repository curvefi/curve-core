from pathlib import Path

from scripts.deploy.deployment_utils import deploy_contract
from settings.config import BASE_DIR, ChainConfig


def deploy_rate_provider(chain_settings: ChainConfig, address_provider_address: str):
    return deploy_contract(
        chain_settings,
        Path(BASE_DIR, "contracts", "helpers", "rate_provider"),
        address_provider_address,
    )
