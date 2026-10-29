# Six-venue arbitrage research platform — integrated lifecycle

## Scope

Active venues: **Orca Whirlpool, Raydium CPMM, Meteora DAMM v2,
PumpSwap, Meteora DLMM, Raydium CLMM**. Meteora DBC (seventh venue)
and Raydium AMM v4 (separate research) are not included in the six-venue
pipeline. This deliberately leaves future adapters additive.

The pipeline composes existing production repository components; it does
not replace the market-state registry or implement a second coordinator.

## Current discovery-to-simulation path

1. **Authenticate direct live-source pool identities.** Read-only
   upstream-backed Surfpool; existing `next_ten_fork_pool_probe.probe`,
   six named venues, exact pool owner, mint and vault validation. Stale
   or rejected identities are not graph edges.
2. **Build token graph.** Existing `opportunity_graph.cycles`
   enumerates bounded closed routes over authenticated pools, preserving
   truncation reporting; these are candidates, never quote-certified routes.
3. **Capture source fixtures and native venue quotes.** Existing
   `m5_distinct_venue_coverage_batch.source_batch` serializes original
   accounts; `m5_source_triangle_quote_ranking.rank` uses
   `fixture_all_venue_signed_quotes.quote_leg` for bounded three-leg
   cycles. Unsupported source pricing is blocked, not estimated.
4. **Rank gross-only candidates.** Preserve unquoted/blocked routes;
   only positive gross candidates progress to the next phase.
   **No fee/slippage/compute/SOL-denominated cost conversion proof has been
   established by this ranking**, so it does not claim net profitability.
5. **Stop the source fork, launch a new `--offline` Surfpool process.**
   Recheck the SHA-256 of every source fixture in the manifest. Reuse
   `offline_batch`, `run_three_venue`, independent signed CPI/
   rollback validation, and source-quote comparisons. Individual failures
   are retained as blocked evidence, never accepted.
6. **Registry/coordinator:** full validated current-state registry
   promotion, net economic rankings, and autonomous routing are **not yet
   implemented by this entrypoint**. Never submit mainnet transactions.

## Running locally (strict process isolation)

Run on localhost with a read-only, upstream-backed Surfpool **only for
the source phase**, with explicitly sourced environment configuration:

```bash
python3 -m arb.six_venue_pipeline --phase source \
  --rpc http://127.0.0.1:8899 \
  --registry arb/pool_registry.json \
  --source-dir /tmp/six-source \
  --amount-in 1000000 --observed-unix "$(date +%s)" \
  --maximum 8 --output /tmp/six-source-report.json
```

**Stop the upstream-backed source fork completely.** Confirm the local
RPC port is closed, then start a **new** `surfpool start --ci --offline
--no-deploy` instance. Never reuse a source-backed process for signed
simulations.

```bash
SURFPOOL_EXPLICITLY_OFFLINE=1 python3 -m arb.six_venue_pipeline \
  --phase offline --rpc http://127.0.0.1:8899 \
  --source-dir /tmp/six-source --signed-dir /tmp/six-signed \
  --output /tmp/six-signed-report.json
```

The two-phase runner is also wired into the manual
[Six-Venue Arbitrage Pipeline Safety](../.github/workflows/six-venue-platform.yml)
GitHub Actions workflow, with separate local fork processes and artifact
uploads. Pull requests run the independent safety/unit tests, not a claim
of live market profitability.

## Acceptance truth table

| Gate | What a positive result establishes | What it does not establish |
| --- | --- | --- |
| Authenticated original pool | Owner/mints/vault identity at an observed slot | Current executable quote |
| Token graph | A possible token cycle on known pool identities | Profit or executable route |
| Source-native quote | A bounded indicative input/output prediction | Realized atomic amount |
| Gross ranking | A source-estimated gross positive roundtrip | Positive net SOL economic return |
| Signed isolated simulation | Genuine signed fork execution, CPI continuity and rollback checks when independently accepted | Live execution permission or future state validity |
| Usable registry | Must reauthenticate state, fees, vaults and signed source capability | Automatically profitable or mainnet-broadcast approved |

All reports have `actionable:false`,
`live_execution_approved:false`, and `broadcast:false`. The platform
does **not** have a mainnet transaction submission operation.
