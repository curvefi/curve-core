# enables targetting specifically 20M gas limit blocks for address.
# set use_big_blocks to False to target smaller blocks (2M gas limit)
# you need hyperliquid-python-sdk python package (use pip or poetry)
import os
import sys
from pathlib import Path
import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange

# Add the project root to Python path so we can import settings
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from settings.config import settings


def main():
    # Get private key from settings (which loads from settings/env file)
    private_key = settings.DEPLOYER_EOA_PRIVATE_KEY
    
    # add your EOA address here:
    address = "0xa8b66231317D8fd2D7Fdf1Ddf0a955b0aC77aE31"  # Replace with your actual EOA address

    # create account from private key
    account: LocalAccount = eth_account.Account.from_key(private_key)
    
    print(f"Using account: {account.address}")
    print(f"Target address: {address}")

    # create hyperliquid exchange object
    exchange = Exchange(account, "https://api.hyperliquid.xyz", account_address=address)

    # set target to either big or small blocks. Status should be 'ok' if successful.
    print("Enabling big blocks (20M gas limit)...")
    result = exchange.use_big_blocks(True)
    print(f"Result: {result}")


if __name__ == "__main__":
    main()
