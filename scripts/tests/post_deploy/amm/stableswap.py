from scripts.tests.post_deploy.utils import check_contracts, get_contract


def test_stableswap_deployment(deployment: dict):
    contracts = {
        k: {**v, "contract": get_contract(v["contract_github_url"], v["address"])} for k, v in deployment.items()
    }
    check_contracts(contracts)

    factory = contracts["factory"]["contract"]

    assert factory.math_implementation() == contracts["math"]["address"]
    assert factory.views_implementation() == contracts["views"]["address"]
    assert factory.pool_implementations(0) == contracts["implementation"]["address"]
    assert factory.metapool_implementations(0) == contracts["meta_implementation"]["address"]
