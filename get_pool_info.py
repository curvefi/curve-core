from pathlib import Path
import json
import boa
from eth_account import Account
import argparse
from decimal import Decimal

from settings.config import BASE_DIR, settings

def format_amount(amount, decimals):
    """Format amount with proper decimals"""
    return Decimal(amount) / Decimal(10 ** decimals)

def get_pool_info(pool_addresses):
    """Get comprehensive pool information for multiple pools"""
    
    # Initialize boa and account
    boa.set_network_env(settings.WEB3_PROVIDER_URL)
    account = Account.from_key(settings.DEPLOYER_EOA_PRIVATE_KEY)
    boa.env.add_account(account)

    pools_data = []
    total_tvl = 0

    for pool_address in pool_addresses:
        try:
            # Load pool contract
            pool = boa.load_partial(
                Path(BASE_DIR, "contracts", "amm", "twocryptoswap", "implementation", "implementation_v_210.vy")
            ).at(pool_address)

            # Get coin contracts to fetch individual coin info
            coin0 = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(pool.coins(0))
            coin1 = boa.load_partial(Path(BASE_DIR, "tutorial", "contracts", "ERC20mock.vy")).at(pool.coins(1))

            # Calculate TVL for this pool
            pool_tvl = format_amount(pool.get_virtual_price(), 18)
            total_tvl += float(pool_tvl)

            # Get pool info
            pool_data = {
                "id": pool_address,
                "address": pool_address,
                "amplificationCoefficient": str(pool.A()),
                "name": pool.name(),
                "symbol": pool.symbol(),
                "totalSupply": pool.totalSupply(),
                "assetTypeName": "CRYPTO",
                "isMetaPool": False,
                "gaugeRewards": [],
                "usdTotal": pool_tvl,
                "gaugeCrvApy": [None, None],
                "implementationAddress": pool_address,
                "implementation": "twocrypto-optimized",
                "coins": [
                    {
                        "address": pool.coins(0),
                        "decimals": str(coin0.decimals()),
                        "symbol": coin0.symbol(),
                        "usdPrice": format_amount(pool.price_oracle(), 18)
                    },
                    {
                        "address": pool.coins(1),
                        "decimals": str(coin1.decimals()),
                        "symbol": coin1.symbol(),
                        "usdPrice": format_amount(pool.price_oracle(), 18)
                    }
                ]
            }
            pools_data.append(pool_data)

        except Exception as e:
            print(f"Error processing pool {pool_address}: {str(e)}")
            continue

    # Construct final response
    response = {
        "poolData": pools_data,
        "tvlAll": total_tvl,
        "tvl": total_tvl
    }
    
    return response

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Get pool information")
    parser.add_argument("--pool_addresses", type=str, nargs='+', required=True, help="List of pool addresses")
    args = parser.parse_args()

    pool_info = get_pool_info(args.pool_addresses)
    
    # Print formatted JSON
    print(json.dumps(pool_info, indent=2, default=str))