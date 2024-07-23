from pathlib import Path

from scripts.deploy.utils import deploy_contract
from settings.config import BASE_DIR


def deploy_metaregistry(chain_name: str, gauge_factory_address: str, gauge_type: int):
    return deploy_contract(
        chain_name,
        "helpers",
        Path(BASE_DIR, "contracts", "registries", "metaregistry"),
        gauge_factory_address,
        gauge_type,
    )
