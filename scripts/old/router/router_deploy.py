#!/usr/bin/python3
import boa


def _add_to_config(router):
    print(router)


def main(WETH):
    # fetch latest version of the router:
    latest_router = ""

    # deploy router
    router = boa.load(
        f"contracts/helpers/router/{latest_router}", WETH
    )  # noqa: F841

    # add to config file:
    _add_to_config(router)


if __name__ == "__main__":
    main(WETH="")
