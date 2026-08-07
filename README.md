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

Scaffold one:

```
python manage.py init prod/mychain
```

It asks for each field, reads `chain_id` from the RPC you give it, checks multicall3 exists
on that chain, and refuses to write anything `ChainConfig` would reject.

Or copy [the example](/settings/chains/examples/example.yaml) into
[settings/chains](/settings/chains) as {chain_name}.yaml and fill it in by hand.

- **network_name** - chain name
- **chain_id** - chain id
- **rollup_type** - can be _op_stack_, _arb_orbit_, _polygon_cdk_, _zksync_, _taiko_ or _not_rollup_. Zksync rollups
  currently aren't fully supported
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

The path is relative to [settings/chains](/settings/chains) and includes the directory.

To see what that would do first:

```
python manage.py deploy all prod/sonic.yaml --dry-run
```

Reports every contract it would deploy, upgrade or reuse, and which steps it would skip.
Needs no key, no RPC and no `settings/env`. Exits non-zero if anything would stop the deploy.

Or via Docker, which builds the environment for you:

```
docker compose up --build
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


## Consuming the registry

`deployments/` is the cross-chain Curve address registry. Two generated files make it
readable without walking the tree or calling the GitHub API with a token:

- [registry/index.json](/registry/index.json) - every chain, its config essentials, and every
  recorded address flattened to `amm.stableswap.factory` keys.
- [registry/schema.json](/registry/schema.json) - JSON Schema for a deployment file, generated
  from the pydantic models.

They live outside `deployments/` on purpose: that directory contains only chain folders, and
consumers enumerate it.

Both are generated. Regenerate after changing any deployment file:

```
python manage.py index          # write both
python manage.py index --check  # fail if either is stale (CI runs this)
```

The index covers every recorded chain, including the ones this repo did not deploy — they are
hand-maintained for curve-api-core, so a registry without them would be less useful than the
directory it replaces. Each carries `deployed_by_core`, set from the same rule `status` uses to
decide what it checks, so filter on that rather than maintaining a list.

## Deployment status and drift

To see what is deployed and what would change if the deployer ran again:

```
python manage.py status                    # every chain, every offline check
python manage.py status --brief            # one line per finding
python manage.py status --summary          # one-row-per-chain matrix
python manage.py status --chain prod/sonic # one chain
python manage.py status --only pending     # a single check
python manage.py status --json out.json    # machine-readable
```

`--brief` prints one line per finding with no explanations, and hides findings whose check
could not run - it says how many, so a shorter report never quietly becomes an emptier one.
`--summary` and `--brief` are alternative renderings and cannot be combined.

On a pull request, CI runs this against the branch and against its base and comments with the
difference, so a fix needs no bookkeeping and a fault already on the base branch never fails a
branch that did not cause it. New `CONFIG` or `REQUIRED` findings fail the build; everything
else reports. To see the same locally:

```
python manage.py status --json head.json
python manage.py compare base.json head.json
```

Read-only — it never sends a transaction, and `manage.py` skips the boa connection for this
command, so it runs on a fresh clone with no `settings/env` and no `DEPLOYER_EOA_PRIVATE_KEY`.
Exits `1` when anything is reported, so it can be used as a CI gate.

Scope is what curve-core deploys. `avalanche`, `fantom` and `x_layer` predate this repo — they
have no [settings/chains](/settings/chains) config and no provenance on any row, so no deploy can
target them and every check ignores them.

Each check is derived from the deployer's own code rather than reimplemented, so the report
cannot drift from what `deploy all` actually does:

| Check | Reports | Derived from |
| --- | --- | --- |
| `PENDING` | A newer `_v_NNN.vy` sits in [contracts](/contracts) than the version recorded for a chain. `deploy all` applies these **automatically** — adding a contract file is enough to change what every chain gets, so run this before merging one. | `fetch_latest_contract()`, `version_a_gt_version_b()` |
| `CONFIG` | A [settings/chains](/settings/chains) file that `ChainConfig` rejects. `deploy all` cannot start on these, and since the config is copied into the deployment file it is usually the root cause of the matching `REQUIRED` finding. | `get_chain_settings()` |
| `CONTRACTS` | Version constants the blueprint path cannot parse, contracts declaring none at all, files named so that `fetch_latest_contract` can never select them, folders holding two unrelated contracts that compete for one slot on their `_v_NNN` digits, and `abi/` entries that no longer match a contract path. | `fetch_latest_contract()`, the regex in `deployment_file.py` |
| `SCHEMA` | Keys in a deployment file that no model declares. Pydantic ignores them and the deployer rewrites files through `model_dump()`, so they are deleted the next time that chain is touched. | the models' own `model_fields` |
| `REQUIRED` | Files that fail validation — the deployer cannot read or update that chain at all. | `DeploymentConfig.model_validate()` |
| `COVERAGE` | Chain configs with no deployment, deployments with no chain config, and `file_name` collisions (that field is curve-api-core's blockchain id, so a collision means one file shadows the other). | |
| `INTEGRITY` | Admin roles that are null, shared between roles, or collapsed onto one address. | |

### On-chain checks

Each needs working RPCs, so each is behind its own flag:

```
python manage.py status --onchain   # every recorded address has bytecode
python manage.py status --wiring    # factory pointers and ownership match the file
python manage.py status --bytecode  # recompile and compare against deployed code
```

`--bytecode` is the only check that proves `contract_path` / `contract_version` /
`evm_version` describe what is really on chain. Normal contracts must match by prefix (the
tail is immutables and constructor args); blueprints must match `blueprint_bytecode` minus
the 10-byte EIP-5202 wrapper that `deploy_via_create2` prepends. It is slow — compilation
is cached per source, but it recompiles every distinct contract.
