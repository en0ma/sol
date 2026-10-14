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
