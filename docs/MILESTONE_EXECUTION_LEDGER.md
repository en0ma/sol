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
- [ ] **B04 — General signed offline verification.** Added integrated signed N-leg Surfpool simulation entry point with generic CPI hop checks and last-instruction negative rollback; actual authenticated 3–6-leg runtime receipts remain outstanding.  Added strict generic N-1 SPL CPI credit/debit reconciliation using existing signed inner-instruction decoder; real 3–6-leg route execution and rollback still need authenticated connected fixture and signed artifact.  Existing legacy/v0 signing is now reused for an arbitrary 2–6-leg ordered instruction sequence with per-hop account-linkage checks; full signed runtime CPI and rollback still pending.  Generic signed N+1 balance/rollback audit added in existing coordinator, but N-leg CPI and signed runtime evidence are still required. Reuse legacy/v0 packet assembly and `simulateTransaction`; extend token-flow accounting and rollback to N intermediate accounts. Test representative 2/3/6-hop cases plus errors; **not** every combinatorial venue chain.
- [ ] **B05 — Record execution limitations faithfully.** Packet size/compute/account limits and input-output drift must block unproven routes, not trigger a false green.

### M5-C — Pricing, discovery and economic research (priority 2, parallel)

- [ ] **C01 — Resolve real source-derived effective fee and liquidity gaps:** CPMM creator-fee placement; Orca/CLMM directional ticks; DLMM bin liquidity; DAMM fee state; PumpSwap effective fees; AMM v4 OpenOrders/PnL. Extend existing decoders, no alternative quote engine.
- [ ] **C02 — Quote-vs-signed empirical parity with aligned amounts and provenance.** Currently **zero independently validated samples**. Fix the precise state/slot/fee provenance blockers; preserve independently verified atomicity as separate evidence.
- [ ] **C03 — Observed costs and downside.** Convert *observed* compute/network/priority fees and route costs into comparable start-token units with verified conversion inputs. Do not infer costs or profitable trades from simulate-only quote outputs.
- [ ] **C04 — Make existing discovery, market registry and opportunity graph supply candidates to the coordinator.** Existing: `arb/raydium_public_pool_discovery.py`, `arb/market_state_registry.py`, `arb/opportunity_graph.py`, `arb/research_engine_pipeline.py`. Wire and harden, don't rewrite.
- [ ] **C05 — Continuous monitoring/indexing (M6)** deferred pending reliable M5 source-state and user's RPC/budget authorization.

## C01 — Repair source-binding assertion order after CI #101

Focused CI #40229037828 failed two newly introduced fee source identity tests because the captured native fee diagnostic had not actually enforced the decoded pool configuration address and venue linkage. Added these checks *before* any native fee claim is accepted, alongside explicit authenticated trade-rate type/range validation. On error all intermediate decoded values are discarded, as the prior C01 evidence rule requires. Regression tests now cover contradictory identities and malformed native trade rates. The unrelated signed execution and rollback audit jobs in #101 succeeded. New commit CI remains pending.

## M5-B01/C02/C03 — Direct execution evidence gates instead of more false completion claims

Added a per-signed-route source-pricing/economics gate that requires all three quote comparisons to exist, requires each to be independently verified rather than merely indicative, and requires separately observed fee provenance, authenticated SOL→start-mint conversion, and net-profit evidence. It attaches precise route-and-venue blockers to the existing signed batch artifact, without changing or duplicating the compiler. Signed CPI/rollback success is recorded independently and is **never interpreted as pricing accuracy or realized economic profit**. Pricing across seven venues remains an open substantial protocol implementation task, and isolated Surfpool cannot prove paid transaction network fees.

## M5-B01 — Raise hard genuine signed venue diversity gate

Following CI #118's independent three-triple CPI/rollback evidence and successful full CI #121, the focused CI's multi-route acceptance threshold now requires **three unique distinct venue triples**, not two. The per-route independent signed acceptance still verifies source pools, SPL CPI and last-hop rollback before a venue triple counts. The eight-source-candidate bound remains a discovery budget, not evidence of eight successful routes. New CI must prove the expanded minimum again.

## M5-B01/C02 — Expand source trial breadth and measure parity without claiming provenance

Increased the genuine source-authenticated distinct-triple CI exploration bound to ten candidates; independent signed CPI/rollback gate still requires at least three unique successful venue triples and does not count attempted candidates. Signed-input quote diagnostic now reports minimum/maximum observed deviations and exact integer matches across computed directional quotes, with explicit **indicative-not-validated** language; rollup separates these diagnostic matches from the zero independently source-validated quote samples. This provides directly measurable errors using real execution amounts, not fabricated source pricing.

## M5-C03 — Native wrapped-SOL denomination is an exact start-mint conversion

The observed signed route economics function now recognizes an authenticated starting mint equal to the native wrapped-SOL mint and uses the exact SPL lamports-per-SOL unit equivalence, **not an inferred exchange rate**. When a separately observed lamport transaction fee is supplied, the cost can be converted exactly into WSOL base units without an external price oracle. Contradictory supplied conversion rates fail closed. For non-WSOL starting mints, an authenticated price conversion remains mandatory. Isolated Surfpool does not produce evidence of paid fees; offline batch leaves that input missing and still blocks actual net profitability.

## M5-C02 — Actual three-pool source-derived quote decoding (not pair-only)

Fixed a functional reason for zero observable per-leg quote comparisons: `extract_pool_states` and `fixture_config_quote_projection.derive` previously accepted only *paired* source fixtures, so all three-venue quote probes failed before reading any CPMM or AMM v4 pricing state. Their native account decoders now operate over either 2- or 3-pool authenticated source manifests, checking each leg's own token mint pair rather than comparing every pool against the initial mint pair. CPMM quote path now feeds only the authenticated matched CPMM state into the existing quote provider, preventing incomplete unrelated venue pricing from blocking its own indicative quote. AMM v4 pricing now binds vault fundamentals by exact pool identity, not list position. Full protocol-exact parity remains unproven; this makes real signed-input comparisons possible on the existing source fixtures without falsely upgrading quote provenance.

## M5-B01/C02/C03 — Signed-route break-even economics and parity observability

Extended the **actual signed** three-venue economics pipeline to derive a break-even total fee/slippage budget denominated in start-mint base units, an empirical gross return in basis points, and fee-free downside break-even budgets. It uses only starting and terminal signed SPL balance deltas (not quotes), preserves unverified cost and price conversion gates, and never marks profit authenticated. The signed per-leg parity report now retains terminal signed output and gross delta with input-aligned probe counts. Route CI summary carries priced/blocked leg counts and break-even budgets per accepted route. These are *observable costs that a route could afford*, not real spent transaction fees; missing SOL conversion and protocol-exact quoting remain blockers.

## M5-B01/C02/C03 — Cross-route signed, pricing and economics evidence rollup

The multi-route isolated signed trial now generates `evidence-rollup.json` alongside the individual receipts. The rollup derives *accepted signed route and distinct venue counts* only from the independent acceptance output, counts **actual** indicative priced legs and missing quote blockers separately, and collects **observed gross start-mint deltas** and precise unavailable fee/conversion blocker counts. Pricing and economic acceptance remain deliberately zero when these gaps persist; broadened route attempts never promote a quote to protocol-exact or a gross delta to net profit. This makes the most consequential missing work visible per CI run without adding a parallel execution engine.

## M5-C02 — Meteora DLMM and DAMM v2 venue quote research models

Three substantive commits add bounded DLMM Q64 price one-bin exact-in estimates (with fee/capacity checks and refusal to cross bins), and DAMM v2 input/output fee-side integer constant-product research math. The generic venue quote adapter delegates to these new independent venue implementations and requires synchronized externally authenticated bin/dynamic-fee evidence and appropriate DAMM curve configuration; no default fee tier or guessed bins. Upstream Meteora documentation notes DLMM bin walks and volatility fees and DAMM fee-denomination differences. These are **indicative prototypes**, not source-decoded end-to-end or validated Surfpool signed quote parity. No coordinator change or broadcast.

## M5-C02 — Parallel venue-native source-bound pricing

Three engineering commits add a venue-only research quote interface for all seven adapters, reuse existing authenticated bounded Orca and Raydium CLMM arithmetic plus PumpSwap's venue-specific virtual-reserve/fee-bucket pricing, and strictly reject unauthenticated DLMM bin traversal or DAMM v2 dynamic fee models. Explicit same-slot boundaries and dynamic-fee provenance are mandatory. The coordinator is untouched. These are source-bound research interfaces and tests, not a claim of seven working protocol-exact signed swap quote paths or actual Surfpool parity runs.

## M5-C02 — Raydium native effective reserves (venue-owned)

At baseline focused CI #163 and non-v4 CI #93, both passed. Inspected upstream Raydium cp-swap PoolState::vault_amount_without_fee: fee liabilities are protocol, fund and creator accumulations owed from each raw SPL vault; using raw vault amounts as invariant reserves is wrong. Three substantive commits implement six packed accrued-fee fields at canonical offsets, a strict venue-local reserve subtraction with underflow checks and source-fixture quote integration. This improves pricing fidelity for creator-fee and trade-fee pools, but exact signed parity against real forks is still separately required. No coordinator fee implementation, broadcasting or funded swaps.

## M5-C02/C03 — Explicit native CPMM rounding models and negative gross economics

The preceding focused CI #152 and non-v4 #82 are green. Three linked commits now compute three alternative *integer* directional CPMM quote treatments from the real source-bound vaults/fee configuration, classify which (if any) agrees with each signed CPI output, and safeguard gross-loss routes against being interpreted as economically recoverable by network fee calculations. CI exercises rounding model classification and the independent SOL fee-payer accounting. Alternative quote agreement is an empirical diagnostic, not verified protocol-exact source execution. Existing signed CPI and rollback admission remain unchanged.

## M5-C02 — Raydium CPMM native vault/fee rounding compared with signed receipts

Three connected engineering commits: source-authenticated CPMM vault reserves and native configured fee ppm now produce a directional integer fee-rounding *output range*; the quote fixture provider carries the bound from the actual selected pool and mint orientation, and accepted three-venue signed CPI output is checked against it. Explicit tests verify both reserve directions, signed boundary comparison, and invalid inputs. Existing signed 3-venue CPI/rollback engine is untouched. This improves source-derived price explanation but creator-fee configurations remain blocked; out-of-range results are not marked protocol-exact parity.

## M5-C02/C03 — Native fee-rounding output interval, validated signed fees and non-WSOL cost sensitivity

Baseline focused CI #146 and non-v4 #76 passed. This three-commit push verifies signed packets before fee-for-message requests, exposes optional fee sensitivity for non-WSOL starts with conversion explicitly unauthenticated, and implements AMM v4 fractional fee *floor-vs-ceiling output interval* from the same source-bound adjusted reserves. Signed per-leg diagnostics now show whether the observed token amount falls within that computed rounding interval. This distinguishes rounding explanations from larger price-model error without incorrectly declaring protocol-exact parity. No network fee is deducted from token output, no simulated fee is treated as paid, and source-derived AMM v4 pricing remains indicative.

## M5-C02/C03 — Three-commit precision and separate-fee-payer accounting

The green preceding baseline is focused CI #143 and non-v4 #73. This push fixes the misleading implication that swap output itself funds transaction fees: signed observed token input/output and gross profit are kept as **unchanged start-mint SPL balances**, with a separate SOL fee-payer asset ledger (paid fee absent on offline simulations, optional quoted signed-message fee explicitly separate). A second commit carries native AMM v4 fractional-fee floor/ceiling intervals and rounding uncertainty into actual signed-leg price diagnostics; no 0-bps match misclassification. CI tests cover both paths and arbitrary non-WSOL starts, for which SOL conversion remains unverified. These are not paid fees or full protocol-exact price proofs.

## M5-C02/C03 — Native pricing linked to signed outputs and bounded fee scenarios

This three-commit iteration extends protocol-native AMM v4 pricing proof with its on-chain u64 numerator/denominator included alongside *actual signed leg input and output* and exact integer deviation; native fraction evidence and observed execution are now linked per leg. Economics derives a fee-inclusive **estimated** WSOL downside curve only when isolated RPC supplied a getFeeForMessage lamport quote for that signed transaction. No simulation-only fee is treated as paid, no price oracle is guessed, and getTransaction evidence is not attributed to the signed offline route without a matching settled transaction signature. CI runs dedicated native-parity, WSOL fee and source-attribution regression tests. All signed CPI/rollback baseline safety gates remain unchanged. This still does not prove fully protocol-exact cross-venue pricing or realized net-profit.

## M5-C01/C02/C03 — Exact AMM v4 native fraction + signed-message fee source

Three functional commits: AMM v4 account-derived quote state now retains the **native on-chain u64 fee numerator and denominator**, allowing exact rational computation over OpenOrders/PnL-adjusted reserves; the quote is also computable when the fee fraction is *not exactly representable as ppm*, rather than incorrectly blocking a legitimate pool. When ppm is exactly representable, the existing approximate model is compared and its delta preserved. It is a protocol-specific integer pricing model but remains **indicative** pending independent signed output parity and timestamp provenance. Signed N-leg simulation now queries *getFeeForMessage* against the exact serialized signed message on **local isolated Surfpool**, preserving the SHA256 message binding and estimated lamport fee separately from actual paid network fees; simulation never establishes paid fees. Gross economics emits this exact message estimate when present but continues to block net profitability without independently observed paid fees and conversion. Focused CI adds lossless fractional math, unavailable estimates, non-ppm pool and isolation tests. Do not mark C01/C02/C03 fully accepted until live-independent source evidence is established.

## M5-C02/C03 — Actual integer signed parity and fee observation boundary

Three substantive engineering commits in this push: (1) signed account quote parity now records signed-minus-source base-unit deltas, exact integer matches and ceiling bps, because truncated 0 bps previously disguised nonzero SPL mismatches; (2) economics now refuses to label a caller-supplied fee rate as independently observed, requires a separately identified Solana fee observation, and preserves simulated scenarios as unverified; (3) the real multi-route batch runner accepts optional per-route fee-observation maps without fabricating fee inputs, and these features run in CI. **No simulated transaction is evidence of actual fee payment**; any source fee observation must be linked to independent evidence and should not turn research into trading approval. Previously accepted signed venue coverage remains the baseline. Protocol-exact pricing remains open; this work improves numerical empirical parity and provenance correctness rather than merely adding a counter.

## M5-B01/C02/C03 — Eight-candidate venue coverage and empirical signed downside

The existing single generic three-venue source/offline CI batch now attempts up to eight diversity-ranked authenticated venue triples (increased from four). Each route summary preserves its venue identity, signed compute usage, independent CPI/rollback acceptance, and gross start-mint SPL delta. The three-leg per-venue quote report counts actually computed directional quote comparisons and identifies both blocked legs and maximum *indicative* error in bps without promoting them to authenticated source-exact pricing. The signed economics report now emits fee-independent **gross downside scenarios** using only observed signed initial/final SPL deltas, even when lamport fees or conversion are unobserved. Net scenarios and profitability remain absent until source-attested cost evidence exists. This directly adds observable route and risk measurements, without making up protocol price or fee accuracy.

## M5-B01/C02/C03 — CI #118 demonstrated three signed venue triples; fix source comparison evidence

Focused CI #118's real Surfpool shard-zero job independently accepted **3 distinct genuine three-venue combinations** with signed CPI continuity and rollback, despite the separate fast unit-test job failing on a mocked missing parity key. The CI evidence reported venue triples DAMM v2/AMM v4/Orca, DLMM/AMM v4/CLMM, and Orca/AMM v4/CPMM. This satisfies the first expansion from one accepted triangle to three; full workflow remained red and cannot count as green. The signed N-leg coordinator now records its independently read **initial SPL balances** in the signed receipt so per-leg quote and economic probes can calculate actual observed output and gross start-mint delta instead of reporting unavailable (zero comparison legs). The source comparison additionally verifies both CPI intermediate received and consumed base units exactly match the pre-signed planned inputs and the initial/terminal SPL snapshot is coherent. Pricing remains indicative: protocol-exact sample count stays zero and net economics remains blocked without observed lamport fee plus independently authenticated SOL conversion.

## B01/C01/C02/C03 — Combined evidence acceptance and observed economics

A strict source/receipt cross-check now checks each independent signed three-venue acceptance again and requires at least two **different venue triples**, not merely different cyclic orientations or pools. Its CI gate fails until there are two genuinely distinct accepted signed combinations; failed or unsigned trials cannot count. Quote diagnostics are still per signed leg, with unsupported source fee/liquidity states reported as blockers, not synthetic accuracy samples. New economics module takes the signed starting/terminal SPL deltas, then requires *separately observed* fee lamports and independently authenticated SOL-to-start-mint conversion before computing integer base-unit cost and downside scenarios. Because an offline simulation does **not** supply paid transaction fees or independent conversion, CI economics reports a blocker rather than inventing profitability. Tests cover both evidence gaps and integer conversion. These are hard acceptance and accounting changes; no source-independent quote sample is claimed.

## B01/C02/C04 — Multi-route source fixture and real signed trial batch

Added `arb/m5_distinct_venue_coverage_batch.py` to export up to 12 genuinely distinct pool-triangle fixture attempts and independently sign and evaluate each exported fixture. Reuses source exporter, universal three-venue offline runner, signed independent CPI/rollback acceptance, and CPI-to-quote diagnostic. Produces one durable receipt per candidate and summary counts of independently accepted routes; absent/failed candidates cannot be counted. Contextual source and offline runs must stay separated. Quote comparison still marks all samples as unverified until source-exact pricing proof is implemented.

## B01/C02/C04 — Multi-candidate signed three-venue expansion and per-leg signed output parity probes

A new coverage trial CLI iterates multiple authenticated three-distinct-venue source candidates in source discovery order, exporting a separate manifest-backed fixture for each and executing each via the existing universal signed N-leg coordinator. Each candidate retains an independent output/error receipt and does not count unless the separate signed CPI + rollback acceptance passes. The loop supports a bounded `--max-triangles` and keeps the existing single-candidate mandatory gate. For each source fixture and signed receipt, a new three-venue parity diagnostic joins signed CPI intermediate outputs to signed exact input amounts, then probes existing account-derived native CPMM/AMM-v4 quote implementations at signed per-leg amounts. Unsupported protocol venues and missing source-effective fee/tick data remain explicitly blocked: no fake protocol-accurate accuracy sample or live execution approval. The source and offline loop are CI wiring work; evidence requires fresh CI logs/artifacts.

## B01/C04 — Three-distinct-venue signed acceptance achieved, now mandatory

**Verified 2026-10-25:** AMM v4 Focused Atomic CI [#109](https://github.com/en0ma/sol/actions/runs/40237125333) passed all jobs. Shard-zero isolated Surfpool output: `SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED`, with `signed_atomic_simulation_verified:true`, `rollback_failure_case_verified:true`, `broadcast:false`. An independently implemented acceptance script printed `{"accepted":true, "signed_cpi_and_rollback":true, "three_distinct_venues":true}`. Non-v4 Adaptive Signed Research [#39](https://github.com/en0ma/sol/actions/runs/40237125388) passed. This is **one** authenticated source three-distinct-venue signed triangle, not all venue combinations, not an economic profitability or quote accuracy proof.

The focused CI source job and shard-zero trial now **require** a triangle and require its independent signed CPI/rollback acceptance; previously the workflow silently skipped both when no triangle was discovered. A missing real authenticated candidate or failed signed execution is therefore a CI failure rather than an absent route. Preserve this hard acceptance gate across subsequent changes.

## B01 — CI #108 genuine signed triangle; repair receipt serialization and gate proof

Focused CI #40236014994 emitted `SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED` for a three-distinct-venue source fixture in the shard-zero offline job. That is meaningful real signed Surfpool execution evidence, but the step subsequently failed while JSON-parsing the receipt because CLI output wrote literal escaped `\\n` after JSON instead of a newline. This prevented the independent acceptance and remaining focused jobs from finishing. Fixed receipt serialization and added a separately implemented three-distinct-venue signed receipt acceptance gate checking source mint topology, distinct pools/programs, source manifest, signed CPI, last-hop failure index, full intermediate consumption and safety flags. CI now invokes it for available source fixtures. **Do not mark B01 accepted until the new CI passes this independent gate.**

## B01 — Source triangle drift diagnosed in real CI #107

Focused CI #40235192608 genuinely discovered 30 three-distinct-venue mint triangles, but source fixture export rejected the first because the second source probe reported a different observed slot. Pool snapshots are collected at different RPC contexts; identical discovery and reprobe slot is not a valid invariant. The exporter now rechecks live pool mint/venue identity and decodes each pool's bytes from the **single contextual companion-account snapshot**, refusing drift there. Candidate slots remain recorded for provenance but are not required to equal the later contextual slot. Actual signed triangle success still unverified; code must be exercised in CI.

## B01 — Real source triangle trial in focused CI

The AMM-v4 focused upstream-backed source job now exports the first authenticated three-distinct-venue closed triangle (if one is available) using the existing read-only probe/exporter; it publishes both the fixture and count. The shard-zero isolated offline Surfpool job consumes this fixture through the signed universal coordinator, prints the actual signed/rollback status and uploads a dedicated route receipt. Missing source graph emits an explicit non-success receipt; a failed signed trial likewise cannot be counted verified. This exploratory path remains non-gating until a real three-distinct-venue receipt is accepted. **No claim of three-venue signed success until the new CI artifact is inspected.**

## B01 — Signed genuine three-distinct-venue runner integration

The existing `next_ten_signed_atomic_offline` runner now accepts `--three-venue-fixture` and reuses the established `simulate_adaptive_n_leg_offline` coordinator, its cumulative signed-prefix observations, SPL CPI ledger, and signed final-hop rollback. All three distinct source pool programs are hydrated from the manifest-bound fixture; the runner checks the hydrated pool mints and uses ephemeral SPL accounts with separate final/initial addresses. The positive route must close A→B→C→A, and the negative rebuild changes only final-hop floor. PumpSwap remains explicitly blocked pending its third-leg owner/account mapping; no claim of a successful three-venue signed route until real CI receipts independently pass. New tests focus on source topology and fail-closed cases. This runner is an opt-in research mode and does not alter historical 42 two-leg directions.

## B01/C04 — Three-distinct-venue source fixture export

Expanded the existing source fixture exporter to accept authenticated three-distinct-venue A→B→C→A candidates. For each selected leg it rechecks the discovered pool identity/slot on upstream-backed local Surfpool and reuses `venue_accounts` to gather venue-specific dependent accounts, then captures **all three pools and dependencies in a single contextual snapshot** with manifest hash and authenticated program ELF account inventory. It refuses changed candidates and missing source accounts. A separate indexed CLI mode emits a three-venue fixture with per-leg evidence and no execution claim. Fast CI mocks the read-only exporter. **Still unverified:** actual three-venue signed CPI/rollback. Next step is adapting the existing runner hydration and the existing generic coordinator to consume this three-pool fixture; do not mark B01 complete.

## B01/C04 — Actual authenticated three-distinct-venue route candidate discovery

The existing read-only source-pool probe now discovers genuine A→B→C→A *mint-graph candidates* involving three different supported venues, using only successful authenticated pool snapshots and observed slots. It rejects two-token alternating loops, reused pool addresses, incomplete source identities and unauthenticated candidate pools. Candidates are exposed directly in the existing probe artifact and are not hardcoded to venue triples. **This is not a signed third-venue execution proof**: the current pair fixture hydrator still supports only two pools, so three-pool fixture export and actual signed coordinator trials are the next blocker. Do not claim B01 complete or count any newly verified three-venue atomic route until CI shows real signed CPI and rollback.

## C01/C02 — Authenticated fixture quote-state joins

The existing fixture quote projection now joins native vault fundamentals to decoded source pools by distinct (venue, pool) identity instead of positional zipping. It rejects duplicate/missing pool identities, mismatched mints/slots, pool/config fee identity drift, and authenticated fee claims without a valid ppm. Regression tests include reversed source inventory order and invalid fee evidence, wired into fast CI. The projection remains indicative and cannot certify source provenance or signed output parity.

## C01 — Native CLMM fee bytes and source binding independent test gate

New focused CI tests exercise the real native CLMM decoder with constructed config-layout bytes, owner verification, on-chain fee bounds and pool/config tick-spacing agreement. The captured fee audit additionally rejects any decoder's returned configuration address that differs from the actual decoded pool reference or returned venue that differs from the source pool venue, then discards partially validated fees. New regression suites are **wired into the fast-safety CI job**, including the previously unconnected CPMM source-fee tests. The evidence remains offline account-layout/fixture evidence; quote accuracy remains zero independent signed comparisons. CI confirmation pending.

## C01 — Native source fee bounds and config identity

Added decoder-level fail-closed integer ppm constraints for both CPMM trade and creator fees, rejecting booleans, negative values and values at/above one million. A fee account must be referenced by a nonempty pool-derived address appearing exactly once in the contextual manifest inventory. The captured-fee diagnostic independently rejects an unauthenticated or out-of-range native trade rate even if a decoder returned a contradictory object. Added native decoder regressions. This does not attest independently sourced RPC or quote parity.

## C01 — Atomic native fee diagnostic claims

When authenticated CPMM/CLMM fee decoding fails at *any* point, the fee row is reset to source pool identity and explicit blocker before returning. Partially decoded (but invalid) trade rates and effective ppm are never leaked as authenticated values. Regression tests cover invalid and contradictory native configurations. This is evidence hygiene, not a source quote-parity pass.

## C01 — Native fee evidentiary consistency

The captured auxiliary-fee audit now rejects duplicate source pool identities, rejects any supposedly authenticated effective fee without an integer ppm in [0, 1,000,000), and rejects unverified creator-fee pricing falsely exporting an effective ppm. Errors remain diagnostic `*_CAPTURED_CONFIG_INVALID` rows and cannot establish quote parity. Tests cover CPMM creator-fee conflicts, CLMM missing authenticated ppm, and duplicate inventory. CI validation pending.

## C01 — Shared native CPMM/CLMM fee diagnostics

The existing captured-fee/compute audit now consumes native Raydium CLMM fee configuration evidence via the *existing* `decode_native_config_fee`, alongside CPMM, without inventing a CLMM creator fee field. Captured CLMM tick-spacing/config inconsistencies are explicitly blocked; the source-blocker aggregator distinguishes malformed native configuration and unverified CLMM fees. This is account-derived fee-field research only, **not** full tick-array liquidity, independent source attestation, protocol-exact output parity, or measured lamport costs. CI status pending.

## C01/C03 — Native CPMM fee evidence and signed compute headroom

The existing native CPMM auxiliary-config diagnostic now retains the account-derived **effective quote fee** only when authenticated (e.g., creator fee zero), and keeps it `null` where creator-fee placement remains unresolved. The signed compute diagnostic reports exact observed CU headroom relative to the protocol ceiling, with `null` when no credible CU evidence exists. Neither compute headroom nor source fee fields are converted into unmeasured lamports/start-mint profits. Empty configuration bytes fail closed. CI evidence pending.

## C01/C02 — Evidence-grounded source-blocker prioritization and compute-bound regression

The focused quote/fee research report now includes deterministic `prioritized_blockers`, containing actual affected route IDs and de-duplicated counts, ranked by missing source receipts, provenance, protocol fee/pricing state and quote continuity. This is a diagnostic queue rather than proof that unknown fees or stale source states are resolved. The captured signed compute diagnostic's stricter `SIGNED_POSITIVE_COMPUTE_MISSING_OR_OVER_LIMIT` sentinel is now correctly asserted by existing tests; added boundary regressions for bogus and valid compute values. CI confirmation pending; quote parity remains zero verified samples.

## C01/C02 — Source quote blocker classification

The existing focused CPMM/v4 signed experiment diagnostics now group actual fixture and receipt failures by provenance, source-derived quote availability, quote amount mismatch, signed SPL continuity and per-leg observed-input price probes. Repeated blockers count once per route and invalid probe inventories fail closed. Captured compute requires a positive value within the transaction limit. These are diagnosis improvements, not independently validated source quotes or fee conversions: quote accuracy remains zero verified samples until external source-vs-signed parity can be authenticated.

## B05 — Signed compute evidence and protocol ceiling

The generic signed adaptive observer and final multi-leg simulator now require positive integer `unitsConsumed` from signed `simulateTransaction` receipts, rejecting missing, boolean, nonnumeric, zero and values above the Solana 1,400,000 CU transaction cap. Observed compute units are retained on positive signed N-leg receipts. No synthetic compute allowance, profitability, priority fee or external source quote claim is inferred. CI regression tests added; commit CI pending.

## CI hardening: signed prefix atomic planner state

CI #40222691178 confirmed the preceding synthetic decoder fix still failed because its per-simulation account index was not reset before the second signed simulation. The corrected mock explicitly resets at each RPC result. The production cumulative observer now commits its planned instruction, amount and next expected index **only after** signing, simulation, all signed touched SPL identity/balance checks and persistent-fork no-mutation verification succeed. This prevents failed prefix probes from leaving partial state and invalidating a retry. A regression repeats a failed index to verify consistent fail-closed behavior. CI confirmation pending.

## CI follow-up: synthetic cumulative prefix fixture

Focused CI #40220902547 failed at `test_prefix_observes_each_signed_cumulative_output`: the mocked SPL decoder incorrectly reused its global account index on the second signed prefix simulation and returned a wrong mint. This is a regression fixture defect, not a reason to weaken the stronger production prefix account-identity checks. Fixture decoder now wraps per signed prefix touched-account count; rerun remains pending.

## Signed cumulative prefix full-account consistency (B01b/A03)

The default signed prefix observer now verifies *every touched* simulated SPL account, not only the next output: input debit matches its signed exact amount, earlier intermediate user balances are fully consumed, and the next output is positive and mint/authority-authenticated. Untouched future accounts may be null, consistent with Solana simulation. This closes a gap where a nonzero earlier residual or incorrect initial debit could silently flow into a later compiled input. Unit regressions cover both. CI validation pending; source-exact quote parity still unverified.

## Independent rollback instruction-index hardening

The three- and four-to-six-hop audits now parse the actual signed negative-control InstructionError index and demand the last swap instruction failed, rather than accepting an arbitrary error substring. Receipts also include a structured negative_failure_instruction_index cross-check. Older receipts without this field are accepted only when the raw error pinpoints the correct instruction. Tests reject early failures and contradictory indices. No trading authorization.

## Signed four-to-six actual evidence and independent acceptance — 2026-10-25

CI #40214148620 produced six positive signed atomic plus failed-final-leg rollback receipts across CPMM↔AMM-v4 **four, five and six swap** trials (two start directions each). All six receipts carry `SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED`, signed CPI intermediate checks, and positive terminal balances; this is authenticated two-pool *alternating interoperability*, not seven-venue route evidence, on-chain runtime-variable inputs, closed arbitrage, or verified quote accuracy. A new independent strict acceptance gate validates all six receipt files and is required to pass in future CI; at commit time its run is not confirmed.

## Four-to-six signed offline exploratory trials

The same source-backed CPMM/v4 runner now accepts `--adaptive-hops 3|4|5|6`, alternates the two source-authenticated pools/mints, uses N+1 distinct SPL token accounts, and builds a last-leg failure instruction on the correct parity without duplicating the engine. CI records 4-, 5-, and 6-leg exploratory receipts separately under `m5-four-to-six-hop-signed-trial-receipts`; these are **not** independently accepted and may fail packet limits or shared-pool state constraints. No success or profitability credit before inspecting artifacts.

## Three-hop verified signed runtime — October 25, 2026

CI [#40212458787](https://github.com/en0ma/sol/actions/runs/40212458787) produced two genuine signed offline **three-hop** receipts with `SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED`. CPMM→v4→CPMM consumed 8,203,755 then 80,666,106 intermediate units, ending with 4,653,406 terminal units; reverse v4→CPMM→v4 consumed 10,119,208 then 80,718,247, ending with 8,168,031 terminal units. Both had zero user intermediate SPL residuals and failed their signed negative controls at instruction index 2. These are A→B→A→B **interoperability paths**, not closed arbitrage nor quote accuracy, and their upstream source slot is not independently attested.

A separate strict independent CI audit of the actual two three-hop receipts is now mandatory; passing overall workflow alone must never award credit. Remaining: route-general 4–6 signed cases, effective-fee and quote parity, and continuous market-state research. No broadcast.

## Three-hop execution blocker from actual CI evidence

CI #40211600343 completed green, but **both** trial receipts in `m5-three-hop-actual-signed-receipts` were BLOCKED with `missing three-account local token snapshot`. That message came from legacy `_post`, which strictly expected three SPL accounts while the real trial provisioned four. Widened the existing synchronized account reader to 3–7 unique aligned accounts, preserving mint/authority, owner and slot checks. A green workflow does not mean three-hop passed. Rerun trial to locate the next actual execution boundary.

## Actual authenticated three-hop research trial

The pre-existing CPMM/v4 pair fixtures now drive A→B→A→B signed three-swap trials in both directions, reusing the first authenticated venue pool on leg three. This uses four distinct ephemeral SPL accounts, the cumulative signed prefix observer and generic N-leg signer/CPI/rollback engine. Evidence artifact: `m5-three-hop-actual-signed-receipts`. Trial execution and acceptance are not yet confirmed; do not promote the route count without signed receipts.

## Execution order and proof of progress

1. Read latest branch, `AGENTS.md`, this ledger, roadmap, both adaptive CI artifacts and failed acceptance logs.
2. Fix **A01** and update actual verified/unverified counts; do not make green atomicity substitute for adaptive continuity.
3. Complete **A02–A03** using existing coordinator/adapter/runner; then **B01–B05** with a single N-leg algorithm.
4. Execute **C01–C04** in parallel when source state and test cases exist.
5. Every meaningful commit: mark only supported checkboxes, cite SHA/run/artifact, record failure or evidence gap in the PR. No more reporting-only "blocker" modules while executable acceptance remains open.

## CI correction — 2026-10-25\n\nFocused CI #40209685513 failed in synthetic N-leg execution test after a deliberate safety hardening: its mocked successful simulation did not supply signed post-account data. The production validator correctly rejected it as `SIGNED_POST_BALANCES_UNVERIFIED`, so the fixture now supplies explicit mocked post balances to reach the intended missing-negative-control branch. Do not relax production validation. CI rerun pending.\n\n## B01b implementation — cumulative signed prefix observation

The shared signed N-leg runner now supplies a default prefix observer when no observer is injected. It builds each next exact-input instruction through the **existing venue adapter**, signs and simulates all prior legs together on the unchanged offline fork, reads the actual intermediate SPL output and passes it to the next leg. It rejects failed/oversized signed prefixes and mutated fork balances; it does not claim true on-chain runtime-variable inputs. Remaining work: authenticated 3–6-leg source fixture and fully verified signed receipt. CI tests are added; actual signed N-leg CI proof is still pending.

## Current signed N-leg runtime integrity

The integrated simulator now validates the actual positive signed post-transaction SPL account snapshots for every boundary, verifies mint/authority identities, exact initial debit, zero intermediate remainder, and positive terminal credit **before** checking negative rollback. Missing simulated account data is rejected; standalone preflights and CPI-only evidence cannot replace terminal reconciliation. Synthetic CPI test corrected to distinguish the pool vault source from the user's intermediate token account. Actual signed three-to-six-leg runtime evidence still pending.

## Current signed N-leg packet regression\n\nCI #40207778125 failed in the synthetic three-hop account-linkage fixture: its mocked account indexes pointed to the wrong slots. Fixed mock instruction indices to match the test account-key table, preserving strict production linkage validation. Re-run CI before marking B04 complete.\n\n## Current independent evidence links

- Historical 42/42 signed atomic: https://github.com/en0ma/sol/actions/runs/40147853880
- CPMM/v4 adaptive 2/2 actual receipts: https://github.com/en0ma/sol/actions/runs/40200874067
- Two-route adaptive acceptance green: https://github.com/en0ma/sol/actions/runs/40201603613
- Focused 12-route adaptive gate failed (not 12/12): https://github.com/en0ma/sol/actions/runs/40202601761
- Non-v4 30-route adaptive workflow green; audit artifacts require review: https://github.com/en0ma/sol/actions/runs/40202601743

All proof concerns local isolated Surfpool signed simulation only. No independently attested source-to-fork quote accuracy and no funded trades.
