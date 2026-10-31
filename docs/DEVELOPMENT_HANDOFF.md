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

## 2026-10-31 local-fork recorded transaction receipt diagnostic
- Implementation: `59e95821b335ac4bcac72a5384750c89d2751210`; tests: `aefe5510ff173f2215268437106247075b483eda`.
- `inspect_local_recorded_transaction_fee` reuses independent signed-wire signature/digest/compute gates, calls only localhost read-only `getTransaction` with the signed first signature, and strictly compares returned base64 transaction **bytes** to the expected signed packet. Validates receipt slot, no execution error, integer `meta.fee`, and bounded `meta.computeUnitsConsumed`. Tampered bytes, missing receipts, wrong encodings, boolean fields and failed executions are rejected in CI-covered adversarial tests.
- Critical: this is local-fork ledger metadata only, not independent mainnet fee-paid evidence, not independent origin authentication, not actual market profitability. `fee_lamports=None`, `independent_fee_paid_verified=False`, `actionable=False`, `broadcast=False` remain permanent. No network broadcast and no registry promotion.
- Verify latest PR HEAD CI before continuing; pending at writing. Next: independent producer/consumer binding between source hash, simulation receipt, local recorded metadata, fee attribution, net SOL/WSOL and SPL poststate; never conflate a recorded local fee with live settled spend.

## 2026-10-31 offline fee-observation correlation checkpoint
- Implementation `3cf37ca9a487887cfa1dff4b3ea3d2c433223f4c`, tests `03fab248e533a4d3ca9a9f87ea58a7acd6d43257`.
- Added `reconcile_local_fee_observations` to the *existing* `arb/signed_route_resource_audit.py`. It correlates exact signed-packet SHA, signature, packet size, and reported simulation CU between local read-only fee quote and exact-byte recorded receipt; exposes divergent quoted/recorded lamports, source hash as explicitly **unverified**, plus diagnostic slots and compute.
- Fail-closed tests cover mismatched packets/signatures, cost type errors, false fee-paid flags, accidentally actionable evidence and invalid source digest.
- **No source authentication or new fee-paid acceptance**: both correlated reports can be from the same untrusted fork. The source hash is only a binding label, not independent proof. `fee_lamports=None`, `net_profitability_verified=False`, `actionable=False`, `broadcast=False`. Existing actual signed acceptance counts unchanged.
- Verify CI on this commit. Next: truly independently authenticate original source snapshot and actual off-chain balance accounting, audit fee-payer lamports and WSOL/SPL poststates at consistent slot, then integrate into shared offline coordinator if and only if independently established.

## 2026-10-31 original-source byte digest checkpoint
- Code `d5e0be801bdc064805ea5ecdd5c1438178e4d0fb`, adversarial test `11dc87c259705276be08e7186fb9ac84a6a475dc`.
- Extended existing `reconcile_local_fee_observations` to optionally require actual original snapshot bytes match their declared SHA-256 (bounded 4 MiB, non-empty, strict bytes). New tests reject tampered content, oversized blobs, wrong Python types, and preserve diagnostic-only outcomes.
- The check proves content-integrity **relative to the supplied digest**, NOT independently authenticated RPC provenance, current state, signed execution SPL acceptance, fee-payer spend, or net profitability. Output `source_snapshot_authenticated=False`, `independent_fee_paid_verified=False`, `fee_lamports=None`, no broadcast.
- CI status: inspect exact current HEAD workflow runs. Next: independently fetch original account owner/mint/vault/slot and match authenticated source manifest and original bytes, then link genuine signed route execution receipts and fee-payer balances under existing fail-closed coordinator.

## 2026-10-31 four final acceptance gates: integrated fail-closed screen
- Code `b9a64daf29afe709f8091d2111bd9176f1a36b39`, tests `fe68fdf5f2111d31112ed1dc46443c1684af0269`, CI `8ff1da5b39cc390bf0110177daa175b5ba89158c`, route identity strengthening `ba0c071380149d409b8f96ea5a34a7100c9490a8`, tests `9a0e5efd790265ddc0e4cc58ea149bccdead271f`.
- New additive `arb/registered_cycle_acceptance.py` integrates original account byte/identity/slot checks, ordered route-leg account identities, existing independently signed SPL gross validator, local diagnostic fee receipt classification and exact six-component candidate costs, in a single four-gate research screen.
- Crucially **four acceptance criteria are NOT completed or met**. Account byte/hash agreement is not upstream owner/mint/vault source authentication; local signed receipt reporting requires genuine independent confirmation; fee source remains local fork, not independently verified paid fee; no positive-net independently accepted real route was established. Screen always returns `accepted_net_profit_base_units=None`, `net_profitability_verified=False`, `actionable=False`, `broadcast=False`. This is not a synthetic profitable route or trade system.
- Test and CI protect fail-closed edges including source tampering, slot/route drift, fraudulent cost values, and fake fee-paid promotion. No mainnet writes, registry promotions or architecture replacements.
- Next true blockers: derive authenticated per-pool owner/mint/vault bytes directly from independent upstream account original program decoder + source slot; bind actual signed Ed25519, CPI, original SPL poststate and negative rollback; independently reconcile fee payer lamport pre/post and all SOL/token costs at a common source/execution state; search actual signed 2–6-leg cycle and accept only genuine fully audited positive net result. If none found, keep pending. Inspect actual current CI outcomes.

## 2026-10-31 next stage — original upstream account source observation
- Implementation `9e84a784f4a570df4c6178bb96a6d5081d633f2d`, adversarial tests `9b7a48677f5f3565f0a8f05e1329ad9f435e8a68`. CI status must be checked for current HEAD.
- Added `inspect_upstream_original_account` to the shared four-gate module: **read-only** upstream HTTPS `getAccountInfo`, exact raw base64 original bytes, explicit expected program owner, verified integer slot at or beyond `minContextSlot`, lamport/executable validation, SHA256 of original bytes and existing content-integrity cross-check. Hostname is returned for provenance context only.
- Critical: an upstream URL by itself is NOT independently authenticated evidence; RPC server results, vault/mint decoding, independent provider comparison, source-to-signed-execution continuity, actual fee-payer debits, complete net costs and demonstrated positive-net routes remain unverified. Returned `upstream_origin_independently_authenticated=False`, all live flags false. Do not promote pools or claim the requested four items complete.
- Next true work: trust-anchored upstream account owner and venue-specific vault/mint parsing; cross-check independently sourced snapshots, same-slot token account state, signed multi-leg receipts, paid-fork-vs-market fee provenance and profitability candidate identification. Continue only evidence-backed runs.


## 2026-10-31 CI signed transaction inventory checkpoint
- Changes on PR #1: `29656dc7` adds `arb/signed_transaction_inventory.py`; `7f603327` adds adversarial regression tests; `9545ec21` wires six-venue CI artifact publishing; `545d1424` fixes shell continuation.
- Reuses existing six-venue source graph/quote selection and independently accepted signed offline Surfpool batch; no replacement coordinator. Emits `transaction-inventory/transactions.json`, `transactions.csv` and `summary.md` from the actual current CI signed run, including signed accepted/rejected counts and observed gross raw start-mint deltas. The CI summary and uploaded artifact retain failed or unknown rows, rather than silently treating positive gross as net profit.
- **No independently verified net P&L yet.** Accepted simulation gross remains `UNKNOWN_COSTS` pending independent network/priority/rent/borrow/tip auditing. Failed signed simulations are `NOT_ESTABLISHED`, not classified as losses. No broadcast, live approval or registry promotions.
- Tests check false net promotion, invalid source index, unsafe broadcast, and signed rejection. Current-head workflow conclusions **pending/unverified at document write time**; a commit or a unit test is not proof of green CI or a fresh accepted simulation.
- Next: inspect current-head CI run, confirm downloaded per-route CSV/JSON really contains current signed outcomes, diagnose any errors, and independently bind the complete start-mint fee ledger to genuine signed execution receipts. Broaden seven-venue coverage without weakening provenance controls.

## 2026-10-31 CI artifact inspection and correction
- Inspected actual artifact `13044025296` from successful Six-Venue run `41202737416` at commit `dc90cb25`; all 15 PR workflows eventually completed successfully. The first inventory contained eight source route rows but only one selected signed attempt, accepted with observed signed gross start-mint delta **-20,201,710 raw units**, 100,809 observed CU, and net cost still unverified. The previous exporter accidentally rendered empty venue names because source `summary.json` supplies `venues`, not `legs`.
- Follow-up commits `f69463c4` and `c2d5a4d7` fix venue extraction, retain all eight source routes including seven unattempted routes (never misrepresent as signed simulations), and add regression tests. New commits require their own CI run verification; do not inherit historical green.
- This demonstrates an observed *gross-loss* signed diagnostic route, not a confirmed net profit or full-cycle opportunity coverage. Until independent expense provenance exists, net-profit classification stays unknown.

## 2026-10-31 expanded signed route coverage
- Implementation `fa12d454` adds explicit `sign_all_quotable` mode to the existing source/offline six-venue pipeline. CI wiring `38698183` enables this mode for the bounded eight-route source run. Source-bound positive-gross routes remain distinguished from nonpositive diagnostic routes; the existing digest-checked handoff freezes every selected index and offline independently recomputes the exact selection. No new simulation engine, no mainnet sends, no implied profitability.
- Intended output: attempts for every *source-quotable* selected route, not every graph cycle. Unquoted/blocked graph routes remain unattempted; no false assertion of full 2–6-leg execution coverage. The transaction inventory retains all source rows and distinguishes attempts.
- Latest CI after this change **pending/unverified at handoff write**. Inspect current HEAD workflow conclusions, signed artifact, and timeout/resource errors; do not inherit previous green. Complete cost-based net profitability remains unverified.

## 2026-10-31 actual expanded artifact and quote blocker attribution
- Inspected artifact `13045296756`, CI run `41207687923`, commit `34977cdb`: 8 authenticated three-venue fixture candidates, only 1 fully source-quotable, 7 quote-blocked, **1** genuine signed accepted offline attempt (index 3 Orca > Raydium CLMM > Raydium CPMM), observed signed SPL gross delta `-20424445` raw WSOL units and `100964` compute units. Indicative quote delta `-10789` raw WSOL units differs from observed signed gross; do not infer quote accuracy or positive economics. Complete verified fee accounting remains absent.
- Quote blocker counts: DAMM v2 source-native scheduler/curve quote unavailable (four routes), DLMM dynamic fee/quote parity unverified (two routes), PumpSwap market-cap fee tier/mode unverified (one route). All seven unattempted routes must remain explicit rather than attributed to simulation failure. Current `sign_all_quotable` correctly signs the sole quotable candidate; it does not expand native price eligibility.
- Code commit `faba37af` and regression `aaf4eae6` bind per-route source quote blocker reasons from original ranking file to JSON/CSV/summary, rejecting mismatched or duplicate route indices. This prevents apparently unexplained unattempted rows from hiding native-pricing gaps.
- **Next engineering priority:** integrate independently authenticated DAMM v2 fee scheduler, DLMM effective dynamic fees and PumpSwap tier/mode source state using existing native quote adapters, then rerun all quotable candidates. Obtain genuinely independent fee-payer pre/post evidence before reporting verified net profit. New HEAD CI pending at writing; do not claim green.

## 2026-10-31 signed inventory economic sign diagnostics
- Commits `c6e6f04d`, `98b50e9e`, `2301930b` classify independently accepted negative gross SPL changes as `GROSS_LOSS_NET_NOT_VERIFIED`, rather than misleading `UNKNOWN_COSTS` alone; still never assert independent paid fees or confirmed net profitability. Add adversarial tests for negative-gross nonpromotion and quote sign mismatch, fix source rank contract test.
- The real expanded source/signed artifact inspected from run `41207687923` contains 8 source routes, 7 quote-blocked (4 DAMM v2, 2 DLMM, 1 PumpSwap), one signed accepted route with gross -20,424,445 raw WSOL and 100,964 CU. No authenticated positive-net route. CI for this commit must be checked, not inherited.

## 2026-10-31 expanded authenticated signed diagnostic execution
- `44511e04`: added explicit opt-in `sign_all_authenticated` to the **existing** six-venue source→offline pipeline, distinct from `sign_all_quotable`. Source phase freezes bounded genuine authenticated three-pool fixture identities and raw-data SHA256; offline phase checks original manifest, fixture digests, ranking, quotation continuity, exact signed indices and provenance before dispatch to existing `offline_batch` signed Surfpool and independent CPI/SPL/rollback auditor. A quote-blocked fixture may yield a signed **diagnostic** execution, never a positive opportunity or protocol-exact quote.
- `8a98ae85`: six-venue CI now uses `--sign-all-authenticated` with bounded `--maximum 8` source fixtures. This may turn seven previously unattempted-but-authenticated triangles into genuine signed simulations without weakening quote eligibility. Actual attempts, signed acceptances and gross deltas MUST be confirmed from new HEAD artifacts; no assumption that all eight pass.
- `71403ab6`: regression exercises two distinct original source indices, one positive gross and one non-positive, and rejects tampering in signed handoff. Existing default mode still follows quote-ranked selection elsewhere.
- This advances real signed diagnostic coverage while **native DAMM/DLMM/PumpSwap source quote blockers remain**. Independent fee-payer pre/post net accounting remains blocked; no classified profitable routes, live action or broadcasts. At writing CI for new HEAD is not yet verified.
