import boa

from scripts.deployment.utils import (
    add_deployment,
    fetch_version,
    get_deployment,
)

# import sys
# sys.path.append("./")


deployment_file = "./example-deployment.yaml"


def deploy_router(WETH):
    # TODO: the following deployment flow needs to be converted into a
    # helper function
    contract_designation = "router"
    latest_contract = fetch_version(contract_designation)
    deployed_address = get_deployment(contract_designation, deployment_file)

    if not deployed_address:
        contract_object = boa.load_partial(latest_contract)

    deployed_contract = contract_object.deploy(WETH)

    add_deployment(contract_designation, deployed_contract, deployment_file)

    # todo: tests for router!
    return False  # True if router is actually deployed


def main():
    deploy_router("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")


if __name__ == "__main__":
    main()
