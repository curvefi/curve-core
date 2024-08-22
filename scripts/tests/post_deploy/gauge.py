from scripts.deploy.deployment_file import DeploymentConfig
from scripts.tests.post_deploy.utils import check_contracts, get_contract


def test_gauge_deployment(deployment: DeploymentConfig):
    current_deployment = deployment.contracts.gauge.child_gauge
    contracts = {
        k: {**v, "contract": get_contract(v["contract_path"], v["address"])}
        for k, v in current_deployment.model_dump().items()
    }
    check_contracts(contracts)

    factory = contracts["factory"]["contract"]

    assert factory.get_implementation() == contracts["implementation"]["address"]

    if deployment.config.dao and deployment.config.dao.crv:
        assert factory.CRV() == deployment.config.dao.crv
