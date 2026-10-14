# Sol — On-chain Solana arbitrage research

Research and simulation only. No live wallet signing or order execution.

## RPC-only policy
All DEX pool state must be read from **Solana programs via Surfpool**. No Raydium, Orca, Jupiter or other DEX web APIs are used by current code. The prior Raydium and Jupiter HTTP scanners were removed in this PR.

## CI
- Offline Surfpool RPC smoke tests and Python unit tests on pushes and PRs.
- Trusted PR/push mainnet-fork CI using secret `SOLANA_MAINNET_RPC_URL`, with local transaction simulation and AMM program deployment/loader checks.
- Configured pool-account ownership checks (`arb/pools.json`), currently empty.
- Unit tests for `getProgramAccounts` result validation. Full unfiltered live program scans are not invoked by default: major AMMs can own very large numbers of accounts and Surfpool/RPC servers may reject them or exhaust rate/response limits.

## On-chain discovery
`arb/discover_onchain.py` calls `getProgramAccounts` on the local Surfpool RPC and rejects mismatched program ownership. It produces **candidate program-owned accounts**, not confirmed swap pools. It intentionally fails when account counts exceed the configured maximum and will need venue-specific discriminator/data-size/memcmp filters before broad live scans are enabled.

```bash
python3 -m unittest discover -s tests -v
# After starting a mainnet Surfpool fork:
python3 -m arb.fork_probe
# Use discovery only with appropriately restricted program/account filters.
```

## Current boundary
Passing tests prove RPC connectivity, deployed program accounts and a local System Program transaction simulation. They do **not** prove executable AMM swaps, prices, triangular routes, or profitable arbitrage. Next implement protocol-specific account decoders, restricted pool queries, quote math, and full atomic swap simulation before considering any execution.
