# Milestone execution ledger — build on completed engines

**Updated:** 2026-10-25  
**Owner:** engineering / subsequent coding agents  
**Status:** authoritative checklist for next PR changes. Read before proposing implementation.  
**Safety:** research and isolated signed simulation ONLY. Never broadcast a transaction or approve trading.

## Rules that stop duplicate work

- **Inspect existing implementation and latest CI artifact before opening a work item.** "Not fully validated" does not mean "not implemented".
- **Reuse** the existing seven venue builders, primary pool decoders, `arb/atomic_graph_coordinator.py`, signed offline runner, independent rollback assessor, and route inventory. Do not replace these or create competing engines.
- Changes must close an **unchecked acceptance item** below. Each PR/commit references a checklist ID and actual evidence (test name, workflow URL, artifact, route count).
- Historical 42/42 two-instruction atomic proof is **DONE** and must remain preserved. It is distinct from adaptive full-output consumption and source-exact quote verification.
- Keep the user's 2–6-leg goal **one generic route algorithm**. Do not write separate engines or 42×5 hardcoded route lists. Varying hop count is a parameter, with small representative integration tests and per-venue adapter checks.
- `actionable:false`, `live_execution_approved:false`, `broadcast:false` always.

## Audited baseline — do not redo

- [x] **DONE-01 — Seven active primary pool decoders.** Orca Whirlpool, Raydium CPMM/CLMM/AMM v4, Meteora DLMM/DAMM v2, PumpSwap. See `arb/execution_target_matrix.py`, `arb/next_ten_fork_pool_probe.py`.
- [x] **DONE-02 — Venue-specific instruction adapters.** `arb/venue_swap_adapter.py` delegates to implemented swap builders for all seven. Keep these, address missing protocol *pricing* state separately.
- [x] **DONE-03 — Atomic transaction infrastructure and rollback.** `arb/atomic_graph_coordinator.py`, `arb/next_ten_signed_atomic_offline.py`, `arb/next_ten_atomic_evidence.py`. Historical 42/42 signed isolated atomic/rollback accepted in CI #40147853880. This proves *two-leg atomicity* rather than adaptive full consumption or live trading.
- [x] **DONE-04 — Two-leg signed amount-adaptive execution capability.** Signed standalone first leg -> its actual SPL output -> second leg amount -> signed atomic simulation with CPI/rollback. Both CPMM↔AMM v4 directions confirmed in CI #40200874067; the new strict two-route gate passed CI #40201603613.
- [x] **DONE-05 — Existing generic 2–6 instruction compiler.** `compile_route` in `arb/atomic_graph_coordinator.py` already accepts 2–6 closed connected legs. That is **not** a 3–6 signed runtime proof.
- [x] **DONE-06 — Generic amount propagation planner module.** `arb/adaptive_route_amount_planner.py` handles 2–6 signed-observation amounts. Today it is a component, **not yet wired** into 3–6-leg signed run.
- [x] **DONE-07 — Seven indicative exact-input quote branches and source-account fundamentals.** `arb/authenticated_quote_provider.py`, `arb/fixture_pool_fundamentals.py`, `arb/fixture_aux_fee_decoder.py`, `arb/raydium_amm_v4_open_orders_reserves.py`. Protocol-exact auxiliary state and real signed quote accuracy are incomplete, **not absent adapters**.
- [x] **DONE-08 — Thirty non-AMM-v4 adaptive trial pipeline.** `.github/workflows/non-v4-adaptive.yml` ran CI #40202601743 with successful jobs including strict `audit-adaptive-30`. Confirm per-route evidence from the acceptance artifact before promoting route counts.
- [x] **DONE-09 — Source fixture manifest, hydration and fail-closed provenance.** Existing source-byte integrity and fork readback are in place; independent upstream authenticity is NOT established.

## Open milestones — implementation and acceptance only

### M5-A — Repair/complete existing adaptive two-leg coverage (priority 0)

- [ ] **A01 — Confirm exact per-route adaptive counts using both actual CI JSON acceptance artifacts.** CI #40202601743 non-v4 strict audit succeeded; CI #40205085522 focused AMM-v4 job failed because acceptance mistakenly selected **24** `remaining` pairs but all 12 AMM-v4 receipts passed (12/24). Fixed selection to only the 12 AMM-v4 pairs; fresh CI rerun pending. Do not conflate the filtered denominator with evidence of other routes. Never report all 42 adaptive passes until both strict artifacts support that.
- [ ] **A02 — Make the generic adaptive route coordinator the default research path.** Eliminate production/research reliance on legacy fixed 1,000 intermediate amount for any newly planned adaptive route. Preserve legacy mode only for labelled historical regression. Use per-leg observed-output planning; fail closed when the preflight state changes or amounts diverge.
- [ ] **A03 — Enforce signed post-execution continuity for every intermediate account.** The actual two-leg gate already exists in `arb/m5_adaptive_signed_acceptance.py`; reuse it. For N hops check each intermediate pair, signed CPI deltas and final balances; verify rollback with a negative control. Do not treat preflight output as in-transaction dynamic binding.

### M5-B — One reusable 2–6-leg route engine (priority 1)

- [x] **B01a — Connect signed-observation planner to existing seven-venue compiler.** Implemented and unit tested; no signed N-leg runtime evidence.
- [ ] **B01b — Integrate generic compiled N-leg plan into signed offline runner.** Two-leg adaptive runner now calls the same coordinator rather than manually setting second input; 3–6 signed runtime path remains open. CI for this integration pending.
- [ ] **B01 — Integrate `adaptive_route_amount_planner.plan` with the existing graph compiler and venue swap adapter.** Inputs: authenticated pool sequence, mint path, ephemeral token-account map, exact initial amount. Outputs: venue-encoded per-leg amounts/floors and signed offline transaction; no duplicated venue logic.
- [ ] **B02 — Specify amount consumption semantics per adapter.** Ordinary exact-input instructions contain signed fixed amounts; observed previous-leg output in standalone preflight is a *planning observation*, not guaranteed real-time variable transfer. Investigate available per-venue consume-entire-balance behavior or explicit on-chain routing program only if proven needed and feasible. No silent residual token balances.
- [ ] **B03 — Generic route termination.** Open connected interoperability paths are now opt-in at the compiler (`require_closed=False`); runtime stop policy remains open.
- [ ] **B03b — Complete runtime route stop policy.** Stop at configured hop limit (2–6), valid terminal mint/strategy goal, or risk/fee rejection; open X→Y→Z paths are allowed for interoperability checks, while closed arbitrage paths require final mint = initial mint. Do not force every research route to return to the start mint.
- [ ] **B04 — General signed offline verification.** Existing legacy/v0 signing is now reused for an arbitrary 2–6-leg ordered instruction sequence with per-hop account-linkage checks; full signed runtime CPI and rollback still pending.  Generic signed N+1 balance/rollback audit added in existing coordinator, but N-leg CPI and signed runtime evidence are still required. Reuse legacy/v0 packet assembly and `simulateTransaction`; extend token-flow accounting and rollback to N intermediate accounts. Test representative 2/3/6-hop cases plus errors; **not** every combinatorial venue chain.
- [ ] **B05 — Record execution limitations faithfully.** Packet size/compute/account limits and input-output drift must block unproven routes, not trigger a false green.

### M5-C — Pricing, discovery and economic research (priority 2, parallel)

- [ ] **C01 — Resolve real source-derived effective fee and liquidity gaps:** CPMM creator-fee placement; Orca/CLMM directional ticks; DLMM bin liquidity; DAMM fee state; PumpSwap effective fees; AMM v4 OpenOrders/PnL. Extend existing decoders, no alternative quote engine.
- [ ] **C02 — Quote-vs-signed empirical parity with aligned amounts and provenance.** Currently **zero independently validated samples**. Fix the precise state/slot/fee provenance blockers; preserve independently verified atomicity as separate evidence.
- [ ] **C03 — Observed costs and downside.** Convert *observed* compute/network/priority fees and route costs into comparable start-token units with verified conversion inputs. Do not infer costs or profitable trades from simulate-only quote outputs.
- [ ] **C04 — Make existing discovery, market registry and opportunity graph supply candidates to the coordinator.** Existing: `arb/raydium_public_pool_discovery.py`, `arb/market_state_registry.py`, `arb/opportunity_graph.py`, `arb/research_engine_pipeline.py`. Wire and harden, don't rewrite.
- [ ] **C05 — Continuous monitoring/indexing (M6)** deferred pending reliable M5 source-state and user's RPC/budget authorization.

## Execution order and proof of progress

1. Read latest branch, `AGENTS.md`, this ledger, roadmap, both adaptive CI artifacts and failed acceptance logs.
2. Fix **A01** and update actual verified/unverified counts; do not make green atomicity substitute for adaptive continuity.
3. Complete **A02–A03** using existing coordinator/adapter/runner; then **B01–B05** with a single N-leg algorithm.
4. Execute **C01–C04** in parallel when source state and test cases exist.
5. Every meaningful commit: mark only supported checkboxes, cite SHA/run/artifact, record failure or evidence gap in the PR. No more reporting-only "blocker" modules while executable acceptance remains open.

## Current independent evidence links

- Historical 42/42 signed atomic: https://github.com/en0ma/sol/actions/runs/40147853880
- CPMM/v4 adaptive 2/2 actual receipts: https://github.com/en0ma/sol/actions/runs/40200874067
- Two-route adaptive acceptance green: https://github.com/en0ma/sol/actions/runs/40201603613
- Focused 12-route adaptive gate failed (not 12/12): https://github.com/en0ma/sol/actions/runs/40202601761
- Non-v4 30-route adaptive workflow green; audit artifacts require review: https://github.com/en0ma/sol/actions/runs/40202601743

All proof concerns local isolated Surfpool signed simulation only. No independently attested source-to-fork quote accuracy and no funded trades.
