from pathlib import Path
import argparse
import boa
from eth_account import Account

from settings.config import BASE_DIR, settings

# Set up boa environment
boa.set_network_env(settings.WEB3_PROVIDER_URL)
account = Account.from_key(settings.DEPLOYER_EOA_PRIVATE_KEY)
boa.env.add_account(account)

# Set up argument parser
parser = argparse.ArgumentParser(description="Deploy a Stableswap-NG pool")
parser.add_argument("--name", type=str, required=True, help="Name of the pool")
parser.add_argument("--symbol", type=str, required=True, help="Symbol for the LP token")
parser.add_argument("--coins", nargs='+', required=True, help="List of coin addresses")
parser.add_argument("--A", type=int, default=200, help="Amplification coefficient")
parser.add_argument("--fee", type=int, default=4000000, help="Trade fee (1e10 precision)")
parser.add_argument("--offpeg_fee_multiplier", type=int, default=20000000000, help="Off-peg fee multiplier")
parser.add_argument("--ma_exp_time", type=int, default=866, help="MA time window")
parser.add_argument("--asset_types", nargs='+', type=int, required=True, help="Asset types for each coin")
parser.add_argument("--method_ids", nargs='+', type=str, required=True, help="Method IDs for rate oracles")
parser.add_argument("--oracles", nargs='+', type=str, required=True, help="Oracle addresses")

args = parser.parse_args()

# Load the factory contract on Fraxtal Testnet
FACTORY_ADDRESS = "0x94CEe64A83102C99c83B19f104a165F4AD5ebd5c"
factory = boa.load_partial(
    Path(BASE_DIR, "contracts", "amm", "stableswap", "factory", "factory_v_100.vy")
).at(FACTORY_ADDRESS)

def convert_method_id_to_bytes(method_id: str) -> bytes:
    """Convert method ID string to bytes4"""
    if method_id == "":
        return b""
    return bytes.fromhex(method_id.replace("0x", ""))

def main():
    # Validate inputs
    assert len(args.coins) >= 2 and len(args.coins) <= 8, "Must have between 2 and 8 coins"
    assert len(args.coins) == len(args.asset_types), "Must have same number of asset types as coins"
    assert len(args.coins) == len(args.method_ids), "Must have same number of method IDs as coins"
    assert len(args.coins) == len(args.oracles), "Must have same number of oracles as coins"
    
    # Convert method IDs to bytes
    method_ids = [convert_method_id_to_bytes(mid) for mid in args.method_ids]
    
    # Deploy the pool
    try:
        pool_address = factory.deploy_plain_pool(
            args.name,                    # _name
            args.symbol,                  # _symbol
            args.coins,                   # _coins
            args.A,                       # _A
            args.fee,                     # _fee
            args.offpeg_fee_multiplier,   # _offpeg_fee_multiplier
            args.ma_exp_time,            # _ma_exp_time
            0,                           # _implementation_idx (using first implementation)
            args.asset_types,            # _asset_types
            method_ids,                  # _method_ids
            args.oracles                 # _oracles
        )
        print(f"Pool deployed successfully at: {pool_address}")
        return pool_address
    except Exception as e:
        print(f"Failed to deploy pool: {str(e)}")
        raise

if __name__ == "__main__":
    main()