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
