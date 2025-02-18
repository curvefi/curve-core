# enables targetting specifically 20M gas limit blocks for address.
# set use_big_blocks to False to target smaller blocks (2M gas limit)
# you need hyperliquid-python-sdk python package (use pip or poetry)
import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange


def main():

    # add the following info:
    account: LocalAccount = eth_account.Account.from_key("your_private_key")
    address = "eoa_address"

    # create hyperliquid exchange objet
    exchange = Exchange(account, "https://api.hyperliquid.xyz", account_address=address)

    # set target to either big or small blocks. Status should be 'ok' if successful.
    print(exchange.use_big_blocks(True))


if __name__ == "__main__":
    main()
