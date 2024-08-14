from scripts.deploy.deployment_file import DeploymentConfig
from scripts.tests.post_deploy.utils import check_contracts, get_contract
from settings.config import RollupType


def test_registries_deployment(deployment: DeploymentConfig, chain_settings):
    contracts_deployment = deployment.contracts
    contracts_deployment = contracts_deployment.model_dump()

    contracts = {
        k: {**v, "contract": get_contract(v["contract_github_url"], v["address"])}
        for k, v in contracts_deployment["registries"].items()
    }
    check_contracts(contracts)

    # <-------------------------- Address Provider -------------------------->
    address_provider = contracts["address_provider"]["contract"]
    fee_receiver = chain_settings.dao.vault
    if chain_settings.rollup_type != RollupType.not_rollup:
        gov_contracts = contracts_deployment.get("governance")
        assert gov_contracts
        assert gov_contracts.get("vault")
        fee_receiver = gov_contracts["vault"]["address"]

    assert address_provider.get_address(2) == contracts_deployment["helpers"]["router"]["address"]
    assert address_provider.get_address(4) == fee_receiver
    assert address_provider.get_address(7) == contracts_deployment["registries"]["metaregistry"]["address"]
    assert address_provider.get_address(11) == contracts_deployment["amm"]["tricryptoswap"]["factory"]["address"]
    assert address_provider.get_address(12) == contracts_deployment["amm"]["stableswap"]["factory"]["address"]
    assert address_provider.get_address(13) == contracts_deployment["amm"]["twocryptoswap"]["factory"]["address"]
    assert address_provider.get_address(18) == contracts_deployment["helpers"]["rate_provider"]["address"]
    assert address_provider.get_address(26) == contracts_deployment["helpers"]["deposit_and_stake_zap"]["address"]
    assert address_provider.get_address(27) == contracts_deployment["helpers"]["stable_swap_meta_zap"]["address"]

    # <-------------------------- Metaregistry -------------------------->
    meta_registry = contracts["metaregistry"]["contract"]

    assert meta_registry.get_registry(0) == contracts["metaregistry"]["registry_handlers"]["stableswap"]["address"]
    assert meta_registry.get_registry(1) == contracts["metaregistry"]["registry_handlers"]["tricryptoswap"]["address"]
    assert meta_registry.get_registry(2) == contracts["metaregistry"]["registry_handlers"]["twocryptoswap"]["address"]
