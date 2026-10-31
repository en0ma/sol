# Development handoff — en0ma/sol

Updated: 2026-10-30 (America/Toronto). PR: https://github.com/en0ma/sol/pull/1
Branch: `feat/surfpool-ci-validation`. Handoff's starting implementation HEAD: `e79de031cace14194b05a1690926a5b01aa037c0`.
**Read the latest PR HEAD and workflow runs first.** This document is historical evidence, never a substitute for current CI results.

## Nonnegotiable contract
- One existing `arb/pool_registry.json`, `arb/atomic_graph_coordinator.py`, existing venue adapters.
- Direct authenticated original source, independently verified native integer/official SDK parity, genuine Ed25519-signed **offline** Surfpool simulated execution, independent CPI/SPL poststate and rollback audits.
- Read-only mainnet source RPC, isolated localhost offline signing RPC. **No mainnet broadcast**, no fabricated receipts, no automatic promotion of stale provenance.
- Every development update must include a venue-by-milestone matrix; don't equate green unit CI with newly signed swap acceptance.

## Venue x milestone matrix (historical evidence; current HEAD must be rechecked)
| Venue | Authenticated source | Independent integer / SDK | Genuine signed trials | Registry signed provenance |
| --- | --- | --- | --- | --- |
| Orca Whirlpool | Yes | Historical established | Historical established, precise per-pool count not recovered | Legacy format |
| Meteora DAMM v2 | Yes | Historical established | Historical established, precise per-pool count not recovered | Legacy format |
| Raydium CPMM | Yes | Historical established | Historical established, precise per-pool count not recovered | Legacy format |
| PumpSwap | Yes | 7 pools | 28, four each | 7 |
| Meteora DLMM | Yes | 6 pools | 24, four each | 6 |
| Raydium CLMM | Yes, restricted single-tick | 7 supported pools | 28, four each | 7 |
| Meteora DBC, seventh research venue | Historical source and SDK/native quote evidence | 6 historical source sets / 24 quotes | 28 user-SPL trials across 7 pools, but only 8 trials/2 pools vault-audited | **0** fully promoted |

## Coordinator checkpoint
- Registered pool reads, circular 2–6-leg enumeration, exact raw-unit native indicative quote propagation/ranking, signed isolated dispatch, 3–6-leg runner integration, CPI/SPL and rollback checks are present.
- Latest pre-cycle commit `e79de031` added regression proving observed signed SPL gross ranking overrides indicative native quote ranking. Fifteen PR workflow runs returned success for that SHA.
- Current signed gross rankings **do not prove net profitability** or current coordinator admission. `arb/six_venue_registry_eligibility.py` intentionally returns zero coordinator-eligible identities pending current source/fee/quote and receipt validation.
- `arb/six_venue_route_economics.py` is only a fail-closed arithmetic checker for externally independently accepted evidence, not a fee collector, a crypto verifier, or proof of live economics.

## This commit cycle
- Added rejection of total cost components summing outside the unsigned 64-bit start-mint accounting domain, while preserving historical signed gross and non-actionable flags; added adversarial regression test.
- Implementation SHA: `c845a75349ef11d2a2a1c13c64c6d4d44b8bea71`.
- Test SHA: `eec2d9bd644d333fcb655a024805f0bae32df931`.
- Verified CI on handoff commit `9f62a63bd179493c87b4c108ff6be216cccdb17f`: **15/15 PR workflow runs completed successfully**. Relevant [Six-Venue Arbitrage Pipeline Safety run](https://github.com/en0ma/sol/actions/runs/41164403447) passed both the contract/test job (including the new economics overflow regression) and the isolated source-to-offline simulation job. [AMM v4 Focused Atomic CI](https://github.com/en0ma/sol/actions/runs/41164403734) also passed. [Seven Venue Acceptance Checkpoint](https://github.com/en0ma/sol/actions/runs/41164403704) passed. Other 12 associated runs also returned `completed/success`. This CI report applies to `9f62a63b`, not necessarily the later documentation-only commit containing this report.
- Relevant check: `.github/workflows/six-venue-platform.yml`, specifically `test_six_venue_route_economics.py`.
- This cycle does **not** claim newly signed routes, complete net fees, or registry promotion.

## Next priority after verifying CI
1. Verify actual current GitHub Actions conclusions; fix any red runs.
2. Independently source and bind fee/priority/rent/borrow/tip expenses in start-mint units to the same offline signed route receipts; missing values or missing independently verified conversion must remain blocked.
3. Build safe provenance bridge for the three historical venues; freshly reauthenticate current source and current quotes before coordinator eligibility.
4. Evaluate genuine 2–6 leg signed offline routes under exact poststate, compute/packet/fee caps, replay-resistant receipts, negative rollback and net economics. Never claim profitable on mainnet.
5. Continue DBC original source/vault-backed signed acceptance separately; historical signed trials are not equivalent to upgraded audited registry promotion.

## Restart instruction
Inspect PR #1 branch HEAD, compare it against the SHAs above, read coordinator/economics/eligibility modules and live CI, run adversarial tests, implement only the next missing accepted gate, push changes, and update **this file every commit cycle** with the implementation commit, actual workflow run IDs/conclusions, tested scope, and the next precise blocker. If GitHub CI is pending, write pending rather than green.

## Follow-on cycle — 2026-10-30/31: WSOL fee-unit reconciliation
- Implementation commit `e82c589640a4601219e38fd37abe1c7e62d636eb`; adversarial regression commit `2fb7d4155ff403802cc712ab9f906dc1b58badd6`.
- Added `reconcile_wsol_lamport_costs` in existing `arb/six_venue_route_economics.py`. Only canonical wrapped SOL (`So11111111111111111111111111111111111111112`) can use the exact identity 1 lamport = 1 raw WSOL unit. When an independently audited lamport inventory is supplied, an inconsistent `network_fee`, `priority_fee`, or `tip` now blocks net arithmetic. The independent audit flag is a caller contract and DOES NOT cryptographically authenticate the actual fee: future receipt auditor must establish it.
- Added tests for matching and mismatching lamport fee values, missing audit flag, wrong mint, boolean substitution and zero-fee fraud.
- No USD/SOL conversion is invented, no signed transaction fee was independently collected in this cycle, no live approval and no registry promotion.
- Verified latest implementation/handoff commit `e37c312907c256a362897cb919efc5e2676009b3`: **15 of 15** associated PR workflows completed with `success`. [Six-Venue Arbitrage Pipeline Safety #41166041085](https://github.com/en0ma/sol/actions/runs/41166041085) passed (including exact cost-accounting regression and signed offline source-to-simulation job); [AMM v4 Focused Atomic CI #41166041171](https://github.com/en0ma/sol/actions/runs/41166041171) passed; [Seven Venue Acceptance Checkpoint #41166041139](https://github.com/en0ma/sol/actions/runs/41166041139) passed. This observed result pertains to `e37c3129` and not automatically to this documentation-only reporting commit.
- Next: independently extract signed fee and compute budget from actual offline transaction and RPC evidence, not arbitrary caller attestations; bind to source digest + transaction signature, then implement fully verified SOL/non-SOL conversion or leave blocked.

## 2026-10-31 signed wire + compute diagnostic checkpoint
Implementation: `4408ca7c0965174b0eeba8a5e999a9592450e04c`; adversarial tests: `4907ab87183a906f0d1e3b1cafc7ea98bafab3ce`; CI wiring: `91e3b425b2fcaba3f239a8d9335f5fc882eb5fc5`.
- New additive `arb/signed_route_resource_audit.py` verifies cryptographic Ed25519 signatures on supplied genuine signed legacy/v0 bytes, an explicit SHA256 wire digest, packet size <=1232 and successful simulation's bounded 1..1,400,000 `unitsConsumed`. Exposes diagnostic compute, packet identity and signature; explicitly returns `fee_lamports: null`, `independent_fee_paid_verified: false`, and all actionable/broadcast flags false.
- Unit tests reject altered signatures, wrong hash, out-of-range compute, noninteger values, failed simulation, malformed wire. CI executes this test on each six-venue PR.
- **This is not independent fee extraction and not proof of a fee paid.** Simulation CU is compute reported by the local fork; it must be bound to an original independently audited receipt, original state and associated signed SPL/rollback evidence. Do not upgrade to net-profitability verification.
- CI status must be obtained for this exact handoff commit from GitHub. Next step: audited RPC transaction fee/compute receipt binding with real transaction identity, then conservative SOL/WSOL economics. Never assume `getFeeForMessage` alone is a paid fee.

## 2026-10-31 next checkpoint: exact signed-message RPC fee quote, offline only
- Implementation `943c62d705eef0d13c9612436200a2d6d23229e4`; regression `f5d997bdafd2e8c9325170df2f3522d3afc61bdf`.
- Extended `arb/signed_route_resource_audit.py` with `quote_signed_message_fee_offline`: validates signed wire/digest and simulation CU, restricts RPC to localhost via existing `local_rpc_only`, queries read-only `getFeeForMessage` using the **exact signed serialized message**, validates integer quote and context slot, returns message SHA256 and quoted lamports. Tests verify exact message, forbid non-local URLs, malformed responses, and paid-fee promotion.
- **Critical limitation:** `getFeeForMessage` is an RPC fee *quote*, NOT a paid fee or independent RPC provenance audit. Every result has `fee_lamports=None`, `independent_fee_paid_verified=False`, `actionable=False`, `broadcast=False`; no result is passed into net profitability as accepted spend. Source digest and signed simulation provenance remain a future integration task.
- CI for this cycle must be checked at the final HEAD, especially the new tests in `Six-Venue Arbitrage Pipeline Safety`. Do not report green before all runs complete. Next milestone: receipt-backed independently verifiable actual fee accounting, including explicit priority-fee and rent attribution; never promote a fee quote.
