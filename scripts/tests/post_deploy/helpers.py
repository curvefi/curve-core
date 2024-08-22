from scripts.deploy.deployment_file import DeploymentConfig
from scripts.tests.post_deploy.utils import check_contracts, get_contract


def test_helpers_deployment(deployment: DeploymentConfig):
    current_deployment = deployment.contracts.helpers
    contracts = {
        k: {**v, "contract": get_contract(v["contract_path"], v["address"])}
        for k, v in current_deployment.model_dump().items()
    }
    check_contracts(contracts)
