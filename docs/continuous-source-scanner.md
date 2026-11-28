# Read-only continuous source scanner

The CI three-hop inventory is a **finite signed evidence test**, not a
continuously running opportunity service. `arb/continuous_source_scanner.py`
is a separate, read-only long-lived coverage process.

## Run against a managed source-backed fork

Start a **locally managed source-backed Surfpool instance** using the documented
local source-fork setup (do not use the offline signer fork for this phase).
Its RPC must be bound to a loopback address.

```bash
python3 -m arb.continuous_source_scanner \
  --rpc http://127.0.0.1:8899 \
  --registry arb/pool_registry.json \
  --output scan-results \
  --interval-seconds 60 \
  --target-unique-starts 200
```

The default `--max-scans 0` continues until the process exits; use
`--max-scans 2` for a finite, reproducible smoke test. Run this process under
your own supervisor (systemd, container orchestrator, etc.) to keep it active
between deployments. GitHub Actions does not provide persistent execution.

The service fails closed on missing source authentication. Any failure writes
`SOURCE_SCAN_FAILED` to `latest.json`, with no inherited successful coverage
counts. `history.jsonl` retains each scan or failure. The source fork remains
read-only, and this scanner does not sign or broadcast transactions.

## Interpreting metrics

- `source_topology_unique_start_mints`: number of **distinct mint addresses**
  with a three-hop closed cycle across source-authenticated pool accounts.
- `selected_graph_unique_start_mints`: distinct mint addresses in the
  currently **bounded 200-route candidate graph**.
- `target_met_on_topology`: whether authenticated topology reaches the
  requested 200-mint target; this is not a tradeability assertion.
- `source_captured_start_mints` and `signed_rollback_verified_start_mints`:
  `null`. Those must be populated by independent source fixture capture and
  signed/rollback verification, not inferred from topology.
- `quoted_routes`: zero. `profitable_routes`: `null` and
  `profitability_status`: `NOT_EVALUATED`. Profit estimates require
  source-bound executable quotes, dynamic trade sizing, pool/transaction fees,
  and freshness checks, and should be reported separately from simulation.

At present the source inventory and graph remain bounded to a curated set of
pools (`maximum_per_venue=48` and a 200-route candidate budget). **This service
does not itself expand the pool registry or guarantee 200 unique start mints.**
The next architecture milestone is authenticated multi-venue discovery beyond
the curated pool set and a cost-aware quote stage. Do not label a route
profitable based on cycle connectivity or an offline simulation alone.

## Operational safeguards

The scanner accepts only loopback RPC addresses, verifies source readiness,
program ownership and pool identities through the existing `probe`, and
never uses `sendTransaction`. Signed offline evidence remains a separate
pipeline and does not approve live execution. Use a scoped, authenticated
source RPC and monitor `latest.json` for stale timestamps/errors.
