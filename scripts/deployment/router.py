import os
import sys

import boa

sys.path.append(".")
from scripts.deployment.utils import deploy_contract


def main():
    deploy_contract(
        "contracts/helpers/router",
        "example-deployment.yaml",
        "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
    )


if __name__ == "__main__":
    main()
