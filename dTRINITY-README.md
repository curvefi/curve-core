## Setup
Make sure you have `env` file at `/settings` directory. Note that it is NOT `.env`

## Deploying new StableSwap-NG pool

Example for dUSD/FRAX
```
python deploy_stableswap_pool.py \
    --name "dUSD-FRAX" \
    --symbol "dUSDFRAX" \
    --coins "0x4D6E79013212F10A026A1FB0b926C9Fd0432b96c" "0x2CAb811d351B4eF492D8C197E09939F1C9f54330" \
    --asset_types 0 0 \
    --method_ids "" "" \
    --oracles "0x0000000000000000000000000000000000000000" "0x0000000000000000000000000000000000000000"
```

#### Deploying new cryptoswap pool
```
python manage.py deploy crypto_pool {chain} {pool name} {pool symbol} {coins separated by comma}
```

Example
```
FXS/dUSD

python manage.py deploy crypto_pool fraxtal_testnet dTrinity_FXS_dUSD FXSDUSD 0x98182ec55Be5091d653F9Df016fb1070add7a16E,0x4D6E79013212F10A026A1FB0b926C9Fd0432b96c
```

## Add liquidity using command
```
python add_liquidity.py --pool_address {pool_address} --amount_token_0 {amount_with_decimals} --amount_token_1 {amount_with_decimals}
```

Example
```
FXS/dUSD

python add_liquidity.py --pool_address 0xD978195666B3863Bed21C240f260d0F8bBa3250b --amount_token_0 2000000000000000000 --amount_token_1 1500000
```

## Swap using command
```
python swap.py --pool_address {pool_address} --views_address {views_address} --amount_token_0 {amount_with_decimals}
```

You can find views address in deployment file at [deployments](/deployments) directory.

Example
```
python swap.py --pool_address 0x1BBB5CAf76868698F00056f48f77ba13cfc5fE8D --views_address 0x0D5824948C879Fa459e41008F66E1Efc9211Cc32 --amount_token_0 4421718
```

## Get pool info to CurveJS using command
```
python get_pool_info.py --pool_addresses {pool_address1} {pool_address2} ...
```

Example
```
python get_pool_info.py --pool_addresses 0x1BBB5CAf76868698F00056f48f77ba13cfc5fE8D 0xD978195666B3863Bed21C240f260d0F8bBa3250b
```
