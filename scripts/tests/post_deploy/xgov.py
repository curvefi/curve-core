from scripts.deploy.deployment_file import DeploymentConfig
from scripts.tests.post_deploy.utils import check_contracts, get_contract


def test_xgov_deployment(deployment: DeploymentConfig):
    current_deployment = deployment.contracts.governance
    if current_deployment is None:
        return

    current_deployment = current_deployment.model_dump()
    current_deployment["relayer"] = current_deployment["relayer"][deployment.config.rollup_type]

    contracts = {
        k: {**v, "contract": get_contract(v["contract_path"], v["address"])} for k, v in current_deployment.items()
    }
    check_contracts(contracts)

    relayer = contracts["relayer"]["contract"]

    assert relayer.OWNERSHIP_AGENT() == deployment.config.dao.ownership_admin
    assert relayer.PARAMETER_AGENT() == deployment.config.dao.parameter_admin
    assert relayer.EMERGENCY_AGENT() == deployment.config.dao.emergency_admin
