# Curve Core

A minimal version of all Curve infrastructure for AMMs in one place.

## Structure

### AMM

- **Stableswap** — pools for 2 tokens with similar value (≈1:1)
- **TwoCrypto** — pools for 2 different tokens
- **TriCrypto** — pools for USD-pegged coins combined with other coins

### Helpers

- **Deposit & Stake Zap** — deposit and stake LPs in one transaction
- **Meta Zap** — easy exchange between an LP token and its underlying tokens
- **Router** — contract for executing complex trades across multiple venues

### Governance

- Agent and relayer for governance from the mainnet DAO
- Vault for receiving fees from pools

### Gauge

- Reward-only gauge for incentives

### Registries

- **MetaRegistry** for AMMs
- **Address Provider** that holds all addresses of factories/DAO/tokens:
  - 2: "Exchange Router"
  - 4: "Fee Distributor"
  - 7: "Metaregistry"
  - 11: "TricryptoNG Factory"
  - 12: "StableswapNG Factory"
  - 13: "TwocryptoNG Factory"
  - 18: "Spot Rate Provider"
  - 19: "CRV Token"
  - 20: "Gauge Factory"
  - 21: "Ownership Admin"
  - 22: "Parameter Admin"
  - 23: "Emergency Admin"
  - 24: "CurveDAO Vault"
  - 25: "crvUSD Token"
  - 26: "Deposit and Stake Zap"
  - 27: "Stableswap Meta Zap"

## Deployment

### Set up environment

#### `.env` file

Put the settings file (`.env`) into the [settings](/settings) directory.  
See the [example](/settings/env.example). It contains the RPC URL for the target chain.

#### Set up Python environment

Project requires **Python 3.11+**.

Install dependencies using Poetry:

```bash
pip install poetry==1.8.3
poetry install
```

#### Chain params file

Put a settings file named `{chain_name}.yaml` into the [settings/chains](/settings/chains) directory.  
See the [example](/settings/chains/example.yaml). It will be used for deployment.

- **network_name** — chain name  
- **chain_id** — chain ID  
- **rollup_type** — one of: _op_stack_, _arb_orbit_, _polygon_cdk_, _zksync_, or `_` (zkSync rollups are not yet fully supported)  
- **native_wrapped_token** — address of the native wrapped token (can be a non-ETH token)  
- **dao** — parameters of contracts already present on chain (the script will deploy x-gov contracts; **CRV** and **crvUSD** should be bridged using native bridges)

Integration parameters:

- **layer** — chain layer (general info)  
- **native_currency_symbol** — symbol of the native token  
- **public_rpc_url** — RPC used in the UI (public only)

#### Deployment

Make sure you have sufficient funds in your account to pay gas on the target chain.

- Export your private key to the environment (do **not** store it in a file):

```bash
export DEPLOYER_EOA_PRIVATE_KEY="<your key>"
```

- Run deployment (replace `chain_name` with the name of the target chain you want to deploy — make sure you added the chain config in the previous step):

```bash
python manage.py deploy all devnet/chain_config_filename.yaml
```

#### Deployment results

Upon success, the script will generate a deployment file with addresses and other info in the [deployments](/deployments) directory.  
The file will have the same name as the chain. ABIs are stored in the [abi](/abi) folder.  
Deployments are reusable, so if something fails, it can be fixed and re-run.  
**NOTE:** Contracts should be verified separately on explorers like **Etherscan**, since API-based verification for **Vyper** contracts is not supported.

### Deploy test pools

Once the infra is deployed, run:

```bash
python manage.py deploy test_pools {chain_name}
```

to deploy test tokens and pools, add liquidity, and **perform** a swap in the test pool.  
**WARNING:** These are test tokens — do not use mocks in production.
