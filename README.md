# Sol — On-chain Solana arbitrage research

Research and simulation only. No live wallet signing or order execution.

## Discovery and verification policy
Venue-wide public APIs and indexes can supply candidate pools without hardcoded token pairs. Candidate liquidity and program IDs are screened, but public API metadata is never trusted as pool authentication or execution proof. Pool account validation and signed swap simulation use the local Surfpool fork. Broad on-chain program scans are deferred until the planned RPC upgrade. See [AGENTS.md](AGENTS.md) and [the architecture roadmap](docs/ROADMAP_AND_ARCHITECTURE.md).

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

## Required on-chain pool readiness gate
The CI fork job now runs `arb.pool_readiness` after writing the Whirlpool verification report. It **intentionally fails** when the report is `NOT_CONFIGURED` or `FAIL`. A passing program loader check and System Program transfer are not sufficient evidence of a testable DEX swap. Pin a real Whirlpool public key in `arb/whirlpool_pools.json` only after its on-chain owner, Whirlpool discriminator, token mints, vaults, and liquidity have been verified. The RPC secret is never printed or stored in artifacts.
