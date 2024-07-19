from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR


def deploy_address_provider(chain_name: str):
    return deploy_contract(Path(BASE_DIR, "contracts", "registries", "address_provider"), chain_name)
