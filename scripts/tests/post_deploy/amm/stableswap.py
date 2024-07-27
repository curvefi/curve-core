from scripts.tests.post_deploy.utils import check_contract_version, check_if_contract_deployed, get_contract


def test_stableswap_deployment(deployment: dict):
    contracts = {
        k: {**v, "contract": get_contract(v["contract_github_url"], v["address"])} for k, v in deployment.items()
    }

    for contract in contracts.values():
        assert check_if_contract_deployed(contract["contract"].address) is True

    for contract in contracts.values():
        assert (
            check_contract_version(contract["contract"], contract["contract_version"], contract["deployment_type"])
            is True
        )
