## Tutorial of deployment curve-lite with an example to arbitrum sepolia
In this tutorial we deployed curve-lite to Arbitrum Sepolia (https://sepolia.arbiscan.io/)

- Configure environment using information from main README
- Deploy mock tokens to ETH sepolia (CRV and crvUSD)
- Bridge them to Arbitrum Sepolia using bridge https://bridge.arbitrum.io/
- Add config file to settings/chains using addresses of bridged tokens
- Run deploy all command

Deployed exmaple pool (cryptoswap) using command
```
python manage.py deploy crypto_pool {chain} {pool name} {pool symbol} {coins separated by comma}
```
(token addresses are bridged tokens)
```
python manage.py deploy crypto_pool tutorial_arb_sepolia Test TST 0x50FB01Ee521b9D22cdcb713a505019f41b8BBFf4,0x92fc3EfE9129675A6d1405519C38b3aDdE4E0ADe
```
