# Sol — Solana arbitrage research

Research-only, **no wallet signing and no live order execution**.

## Phase 1
- Surfpool RPC smoke test in GitHub Actions.
- Integer-base-unit triangular and roundtrip PnL evaluator with automated unit tests.
- Read-only Jupiter quote scanner for SOL/USDC round trips.
- Venue discovery list in `arb/venues.json`.

## Test locally
```bash
python3 -m unittest discover -s tests -v
```

## Read-only indicative scan
Use a Jupiter API key (set locally as an environment variable, never commit secrets):
```bash
export JUPITER_API_KEY=your_key
python3 -m arb.scanner
```
The scanner requests **sequential** offchain quotes from Jupiter Metis and reports a simulated return in SOL lamports after a configurable estimated SOL cost. It does not prove atomic execution, account availability, priority fee sufficiency, or market profit. The adapter does not yet force venue diversity. Some proprietary AMMs require dedicated adapters and caller-specific simulation. Surfpool offline mode cannot fetch live pool state: realistic fork tests require an RPC datasource and captured account fixtures.

## Next steps
- Implement venue-specific state decoders, exact-in quote math, and per-pool addresses.
- Reproduce the same route in one atomic transaction via Surfpool using forked state.
- Account for compute units, token account rents, fees, tips and failure rate.
- Add risk limits before any live trading.

## Fork verification (manual GitHub Actions job)

The `mainnet-fork-probe` job runs only through **Actions → Surfpool CI → Run workflow**. Before running, add a repository Actions secret named `SOLANA_MAINNET_RPC_URL` with a private mainnet RPC HTTPS URL. Surfpool uses this datasource to lazily fetch real mainnet program/account state.

The probe verifies that the configured Meteora DLMM, Orca Whirlpool, Raydium CLMM, Raydium CPMM, and Meteora DAMM v2 program accounts are executable. To inspect **real pools**, add verified entries to `arb/pools.json` using:
```json
{"name":"Verified pool label","venue":"Orca Whirlpools","address":"REAL_BASE58_POOL_ADDRESS"}
```
The pool probe fails on missing accounts or unexpected owners. No pool addresses are committed yet, so passing the program-account probe is **not** validation of any pool price or swap route.

GitHub push/PR CI separately runs Surfpool offline RPC tests and local PnL/RPC unit tests, without fetching mainnet state. Do not treat any of these as successful live-trade simulations. Future work: ingest verified pool listings, decode fee/liquidity state, build atomic swap instructions, simulate transactions on the fork, and reconcile failure/priority costs.

## Live pool discovery (Raydium)
After starting Surfpool in fork mode, run:
```bash
python3 -m arb.discover_raydium --output /tmp/discovered-pools.json
POOL_MANIFEST=/tmp/discovered-pools.json python3 -m arb.fork_probe
```
Pool metadata comes from Raydium API v3; the script requires a local Surfpool account read to confirm actual owners. It currently discovers only Raydium CLMM/CPMM SOL-USDC pools. The manual GitHub Actions fork job performs these steps with the `SOLANA_MAINNET_RPC_URL` secret. No credentials are embedded in source. Pool discovery may fail when public API fields change, forked state is unavailable, RPC quotas are exhausted, or no matching pools exist. A passing result is **not** an executable swap or proof of profit.
