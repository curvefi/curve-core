from scripts.tests.post_deploy.utils import check_contracts, get_contract


def test_helpers_deployment(deployment: dict):
    contracts = {
        k: {**v, "contract": get_contract(v["contract_github_url"], v["address"])} for k, v in deployment.items()
    }
    check_contracts(contracts)
