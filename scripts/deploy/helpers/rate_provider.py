from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR


def deploy_rate_provider(chain_name: str, address_provider_address: str):
    return deploy_contract(
        chain_name,
        Path(BASE_DIR, "contracts", "helpers", "rate_provider"),
        address_provider_address,
    )
