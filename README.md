# Setup Guide: Running the Hyperliquid Big Blocks Script

## Prerequisites
- **Python 3.11+** (this project requires Python 3.11 or higher)
- **Homebrew** (for macOS users)

## Step-by-Step Setup

### 1. Install Python 3.11+
```bash
# Check your current Python version
python --version

# If you need Python 3.11+ on macOS:
brew install python@3.11
```

### 2. Install Poetry
```bash
python3.11 -m pip install poetry==1.8.3
```

### 3. Set up the Python Environment
```bash
# Configure Poetry to use Python 3.11
poetry env use python3.11

# Install all project dependencies
poetry install
```

### 4. Add the Required Package
```bash
# Add the Hyperliquid SDK
poetry add hyperliquid-python-sdk
```

### 5. Configure Your Environment
Create a `settings/env` file with your credentials:
```
WEB3_PROVIDER_URL=your_rpc_url_here
DEPLOYER_EOA_PRIVATE_KEY=your_private_key_here
```

**Replace:**
- `your_private_key_here` with your actual private key (without 0x prefix)
- `your_rpc_url_here` with any RPC endpoint (required by the project structure, but not used by this specific script)

### 6. Update the Script
Edit `scripts/utils/hyperevm_enable_big_blocks.py` and replace:
```python
address = "YOUR_EOA_ADDRESS_HERE"
```
with your actual Ethereum address (the address corresponding to your private key).

### 7. Register Your Wallet on Hyperliquid
- Go to [app.hyperliquid.xyz](https://app.hyperliquid.xyz)
- Connect your wallet
- Complete any required setup/deposit to register your wallet

### 8. Run the Script
```bash
poetry run python scripts/utils/hyperevm_enable_big_blocks.py
```

**Expected Success Output:**
```
Using account: 0x...
Target address: 0x...
Enabling big blocks (20M gas limit)...
Result: {'status': 'ok', 'response': {'type': 'default'}}
```

## Troubleshooting
- **"User does not exist" error:** Your wallet needs to be registered on Hyperliquid first (Step 7)
- **Environment variable errors:** Make sure your `settings/env` file is properly configured
- **Python version errors:** Ensure you're using Python 3.11+

---

That's it! Your wallet will now be configured for 20M gas limit blocks instead of the default 2M gas limit on Hyperliquid HyperEVM.

### ============================ Existing README ⬇️ ================================
# Curve Core

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

### Governance

- Agent and relayer for governance from mainnet DAO
- Vault for fee receiving from pools

### Gauge

- Reward-only gauge for incentives

### Registries

- Metaregistry for AMMs
- Address provider that has all address of factories/DAO/tokens:
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

- **network_name** - chain name
- **chain_id** - chain id
- **rollup_type** - can be _op_stack_, _arb_orbit_, _polygon_cdk_, _zksync_ or "\_". Zksync rollups currently aren't
  fully supported
- **native_wrapped_token** - address of native wrapped token (can be non-eth token)
- **dao** - params of contracts already present on chain (script will deploy x-gov contracts, CRV and crvUSD should
  be bridged using native bridges)

Integration parameters

- **layer** - chain layer (general info)
- **native_currency_symbol** - symbol of native token
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
python manage.py deploy all devnet/chain_config_filename.yaml
```

#### Deployment results

Upon success, script will generate deployment file with address and other info in [deployments](/deployments) directory.
File will have the same name as chain. ABI is stored in [abi](/abi) folder.
Deployments are reusable, so if something fails, it can be fixed and rerun.
**NOTE:** contracts should be verified separately on explorers like etherscan since it doesn't support Vyper contract
verification by API.


### Deploy test pools
When infra is deployed, run
```
python manage.py deploy test_pools {chain_name}
```
to deploy test tokens and pools + add liquidity and permorm a swap in test pool. WARNING!: these are test tokens, don't
use mocks in production.
