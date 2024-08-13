from scripts.deploy.deployment_file import DeploymentConfig
from scripts.tests.post_deploy.utils import check_contracts, get_contract


def test_tricrypto_deployment(deployment: DeploymentConfig):
    current_deployment = deployment.contracts.amm.tricryptoswap

    contracts = {
        k: {**v, "contract": get_contract(v["contract_github_url"], v["address"])}
        for k, v in current_deployment.model_dump().items()
    }
    check_contracts(contracts)

    factory = contracts["factory"]["contract"]

    assert factory.math_implementation() == contracts["math"]["address"]
    assert factory.views_implementation() == contracts["views"]["address"]
    assert factory.pool_implementations(0) == contracts["implementation"]["address"]
