# Curve Lite

A minimal version of all curve infrastructure for AMM in one place.

## Structure

### AMM
- Stableswap - pools for 2 tokens with similar value (1~1)
- Twocrypto - pools for 2 different tokens
- Tricrypto - pools for USD-pegged coins combined with any coins

### Helpers
- Deposit and Stake Zap - for depositing and staking LPs in one tx
- Meta Zap - for easy exchange between LP and underlying tokens
- Router - router contract for executing complicated trades using different places


## Deployment

### Set up environment

#### Env file
Put settings file ("_env_") into [settings](/settings) directory.
[Example](/settings/env.example). It contains RPC url for target chain.

#### Set up Python environment

Project requires Python 3.11+

Install dependencies using poetry

```
pip install poetry==1.8.3
poetry install
```

#### Chain params file

Put settings file {chain_name}.yaml into [settings/chains](/settings/chains) directory.
[Example](/settings/chains/example.yaml). It will be used for deployment.

- **chain** - chain name
- **chain_id** - chain id
- **layer** - chain layer (general info)
- **rollup_type** - can be _op_stack_, _arb_orbit_, _polygon_cdk_, _zksync_ or "_". Zksync rollups currently aren't 
fully supported
- **weth** - address of native wrapped token (can be non-eth token)
- **owner** - address that will be owner of contract (Curve DAO)
- **fee_receiver** - address that will receive fees (Curve admin)

Integration parameters
- **native_currency_symbol** - symbol of native token
- **native_currency_coingecko_id** - name of native token in coingecko (for fetching usd prices)
- **platform_coingecko_id** - coingecko chain name
- **public_rpc_url** - rpc used in UI (only public)

#### Deployment
Make sure you have funds at your account for gas at target chain.

- Export private key to env (don't store it in file!)
```
export DEPLOYER_EOA_PRIVATE_KEY={your key}
```
- Run deployment (replace chain_name with name of target chain you want to deploy - make sure you added chain config for
this chain in previous step!)
```
python manage.py deploy all {chain_name}
```

#### Deployment results
Upon success, script will generate deployment file with address and other info in [deployments](/deployments) directory.
File will have the same name as chain. ABI is stored in [abi](/abi) folder.
Deployments are reusable, so if something fails, it can be fixed and rerun.
