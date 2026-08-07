# Curve Core

A minimal version of all Curve infrastructure for AMM in one place.

## Structure

### AMM

- **Stableswap** — pools for 2 tokens with similar value (≈1:1)
- **Twocrypto** — pools for 2 different tokens
- **Tricrypto** — pools for USD-pegged coins combined with any coins

### Helpers

- **Deposit and Stake Zap** — deposit and stake LPs in one tx
- **Meta Zap** — easy exchange between LP and underlying tokens
- **Router** — execute complex trades across different venues

### Governance

- **Agent** and **Relayer** for governance from mainnet DAO
- **Vault** for receiving fees from pools

### Gauge

- **Reward-only gauge** for incentives

### Registries

- **Metaregistry** for AMMs
- **Address provider** that contains all addresses of factories/DAO/tokens:
  - 2: “Exchange Router”
  - 4: “Fee Distributor”
  - 7: “Metaregistry”
  - 11: “TricryptoNG Factory”
  - 12: “StableswapNG Factory”
  - 13: “TwocryptoNG Factory”
  - 18: “Spot Rate Provider”
  - 19: “CRV Token”
  - 20: “Gauge Factory”
  - 21: “Ownership Admin”
  - 22: “Parameter Admin”
  - 23: “Emergency Admin”
  - 24: “CurveDAO Vault”
  - 25: “crvUSD Token”
  - 26: “Deposit and Stake Zap”
  - 27: “Stableswap Meta Zap”

## Deployment

### Set up environment

#### Env file

Put a settings file (`env`) into the [settings](/settings) directory.  
[Example](/settings/env.example). It contains the RPC URL for the target chain.

#### Set up Python environment

Project requires **Python 3.11+**.

Install dependencies using Poetry:

```bash
pip install poetry==1.8.3
poetry install
```

#### Chain params file

Put a settings file `{chain_name}.yaml` into the [settings/chains](/settings/chains) directory.  
[Example](/settings/chains/example.yaml). It will be used for deployment.

- **network_name** — chain name
- **chain_id** — chain ID
- **rollup_type** — one of `_op_stack_`, `_arb_orbit_`, `_polygon_cdk_`, `_zksync_`, or `_`  
  ZKSync rollups are currently not fully supported
- **native_wrapped_token** — address of the wrapped native token (can be a non-ETH token)
- **dao** — parameters of contracts already present on chain  
  (the script will deploy x-gov contracts; **CRV** and **crvUSD** should be bridged using native bridges)

Integration parameters:

- **layer** — chain layer (general info)
- **native_currency_symbol** — symbol of the native token
- **public_rpc_url** — RPC used in UI (must be public)

#### Deployment

Make sure you have sufficient funds for gas on the target chain.

- Export your private key to the environment (don’t store it in a file):

```bash
export DEPLOYER_EOA_PRIVATE_KEY=<your_private_key>
```

- Run deployment (replace `devnet/chain_config_filename.yaml` with your chain config path; ensure you added the chain config in the previous step):

```bash
python manage.py deploy all devnet/chain_config_filename.yaml
```

#### Deployment results

Upon success, the script will generate a deployment file with addresses and other info in the [deployments](/deployments) directory.  
The file will have the same name as the chain. ABIs are stored in the [abi](/abi) folder.  
Deployments are reusable; if something fails, it can be fixed and rerun.  
**Note:** Contracts should be verified separately on explorers like Etherscan, since API verification for Vyper contracts is not supported.

### Deploy test pools

When the infrastructure is deployed, run:

```bash
python manage.py deploy test_pools {chain_name}
```

This deploys test tokens and pools, adds liquidity, and performs a swap in a test pool.  
**Warning:** These are test tokens; do not use mocks in production.
