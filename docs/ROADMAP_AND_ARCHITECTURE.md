# Sol — Agreed architecture, acceptance criteria and milestone roadmap

**Status:** design intent and engineering targets, not a claim of production readiness.  
**Last consolidated:** 2026-10-25.  
**Applies to:** all subsequent contributors, coding agents and conversations. Read with root [AGENTS.md](../AGENTS.md).

## Scope decision — 2026-10-23 (supersedes earlier eight-venue requirements)

**User-approved active scope: seven venues.** Orca deprecated its original Token Swap v1/standard pools and migrated its supported liquidity focus to Whirlpools. Retire `orca_token_swap_v1` from mandatory discovery, fork authentication, standalone signed execution, and atomic pair acceptance. Preserve its existing adapter and optional legacy tests for reference, but **do not count it as an active eighth venue** or spend active CI/API budget seeking v1 pools. Deprecation does not establish that no old onchain pools exist.

**Active set:** `orca` (Whirlpool), `raydium_cpmm`, `raydium_clmm`, `meteora_dlmm`, `meteora_damm_v2`, `pumpswap`, `raydium_amm_v4`.

**Revised acceptance:** 7 pool decoder and builder implementations, seven onchain-authenticated venue snapshots, seven signed standalone local-fork swap proofs, and **42 ordered cross-venue atomic directions** (21 unordered pairs), each subject to shared-token route feasibility, successful X→Y→Z evidence, and negative rollback tests. Missing compatible routes must be reported distinctly from broken adapters. Do not upgrade historical success or mocked unit-test gates.

Earlier sections below describing **eight** venues, **56** ordered pairs, or Orca v1 mandatory discovery are **historical superseded requirements**. The source of truth for active targets is `arb/execution_target_matrix.py`. All work stays simulation-only with `actionable=false`, `live_execution_approved=false`, `broadcast=false`.

## Milestone transition — 2026-10-25

**M4 completed:** Signed, isolated Surfpool execution and independent rollback evidence
were accepted for all 42 active ordered venue pairs in a single CI run
([strict full regression #40147853880](https://github.com/en0ma/sol/actions/runs/40147853880)).
This is simulation-only and not live profitability evidence.

**M5 now active — opportunity research, not execution.**
Build fresh mint-agnostic pool candidate coverage, amount-aware quotes per venue,
common-start-mint fee/compute/slippage cost conversion, stale quote rejection,
depth/price-impact checks, and compare quoted outcomes with fresh atomic simulation
before accepting *research candidates*. The initial `arb/opportunity_research.py`
is a conservative, pure boundary checker: it cannot originate real quotes,
does not prove profitability, and refuses incomplete or mismatched cost units.
A positive declared-cost estimate is NOT execution approval.
No mainnet transaction broadcasts or funded execution wallets.

**M6 remains deferred:** stronger RPC and production indexing must follow M5
evidence and an explicit budget/authorization decision.

## Agreed operating pipeline — 2026-10-25

Maintain these **distinct**, cooperating engines in this order:
1. Pool discovery engine (all seven active venue feeds, bounded and mint-agnostic).
2. Live pool-state registry (source-authenticated pools, token mints, liquidity, fees, reserves, prices, ticks/bins, slots and freshness).
3. Graph and route builder (tokens as vertices, specific pools as directed edges, connected cycles).
4. Atomic swap engine (venue-specific instruction builders; shared legacy/v0 transaction packing).
5. Signed simulation and independent verification (SPL balances, fees, compute, slippage, ordered top-level invocation and rollback).
6. Execution decision (deliberately **disabled** under current simulation-only authorization).
7. Continuous discovery, refresh and research evaluation (later monitored service).

**Pre-atomic research stage:** amount-aware venue quotes and conservative common-mint
net-cost screening rank candidates *before* invoking the expensive signed
simulation stage. Quote ranking is not execution authorization.

**Current implementation boundary:** `arb/research_engine_pipeline.py` is
an offline dependency-injected integration skeleton over authenticated snapshots,
`arb.opportunity_graph`, quote screening and the existing independent receipt
assessor. It does not claim real-time feeds, persistent registry, all-venue
quotes, continuous monitoring, or profitable opportunities. Do not promote
mocked providers into production evidence. Full venue integration and data
freshness remain the active M5 work.

## 1. Mission and non-goals

Build a Solana **simulation-only** research and verification system capable of discovering pools across seven active DEX venue implementations, authenticating their on-chain state, decoding them, constructing valid swap instructions, verifying each venue's signed standalone swap simulation, and proving **atomic, ordered, two-venue swaps** on a local Surfpool mainnet fork. Eventually use fresh pool coverage to study arbitrage opportunities, but **profitable discovery, trade execution, and live broadcasting are not acceptance criteria for the current implementation phase**.

Do not broadcast real transactions, use funded execution wallets, or treat simulated profitability as live-trading approval. All output defaults: `actionable=false`, `live_execution_approved=false`, `broadcast=false`. Explicit future authorization and a separate risk/security review would be required to change that boundary.

## 2. Original eight-venue scope (historical; superseded by seven-venue decision above)

The seven required active protocol adapters are:

1. `orca` — Orca Whirlpool
2. `raydium_cpmm` — Raydium CPMM
3. `raydium_clmm` — Raydium CLMM
4. `meteora_dlmm` — Meteora DLMM
5. `meteora_damm_v2` — Meteora DAMM v2
6. `pumpswap` — PumpSwap
7. `raydium_amm_v4` — Raydium legacy AMM v4
**Archived optional adapter:** `orca_token_swap_v1` — Orca legacy Token Swap v1 (deprecated in 2023; excluded from mandatory discovery and execution).

Do not conflate a venue family with an instruction format; protocol-specific accounts, authority derivation, fee models, token-program handling and instruction builders differ. `arb/execution_target_matrix.py` defines the ordered target list. Raydium AMM v4 remains required; deprecated Orca Token Swap v1 does not expand the active target or block completion.

**Updated scope, October 23, 2026:** User confirmed **seven active venues; 21 unordered and 42 ordered atomic venue pair tests**. Orca legacy Token Swap v1 is archived optional support. Existing source/tests remain available but its public API discovery and onchain owner screening are removed from mandatory CI. The original historical 8-venue observations below are retained as background only and must not be treated as current acceptance targets. Bundle substantial, coherent work before each CI push rather than committing narrow changes that repeatedly restart expensive forks. Signed standalone execution with real token deltas and ordered atomic execution/rollback remain incomplete and mandatory for the seven active venues.

## 3. Pool discovery: venue-wide, fresh and token-agnostic

**Agreed direction:** never restrict discovery to hardcoded SOL/USDC, other predetermined mint pairs, or a static pool registry. New tokens and pools should become discoverable as they launch.

- Enumerate available pools **per venue** using the venue's public API or a reputable index that supports **venue-wide listing**, preferably sorted by liquidity or recent creation; paginate with bounded requests, rate limiting, timeouts, retry/backoff and deduplication. Do not silently substitute a mint-pair lookup for venue-wide enumeration. Some APIs are incomplete or delayed: record source, fetch time, pagination coverage and truncation.
- Filter for expected program ID/venue, structurally valid distinct mint keys, nonzero liquidity, and a **configurable USD liquidity floor**; rank by liquidity and/or recency. A $10,000 default is an initial testing heuristic, **not** a universal token-legitimacy rule. Preserve discoverability of new low-liquidity pools through a separate recent-pool queue or configurable lower threshold, rather than permanently excluding launches.
- Check pool activity, initialized status, token-program compatibility, vault mints and authorities, reserves, protocol-specific configuration, account owners and (where relevant) OpenBook market state and PDAs. Treat public metadata, USD TVL, price and fee estimates as **untrusted hints** until reconciled with local-fork on-chain data.
- Use discovered pool IDs to fetch **specific on-chain accounts** through Surfpool, avoiding expensive unrestricted `getProgramAccounts` scans under the current free-tier RPC. On-chain account authentication is still required for execution verification; only **exhaustive on-chain pool discovery** is deferred.
- Build independent discovery adapters for **all seven active** venues, or explicitly document missing/limited public API support and use a bounded third-party index/fallback. Normalize into a common candidate schema: venue, program ID, pool ID, token mints, liquidity estimate, source, discovered/fetched timestamp, validation status and reason codes. Deduplicate by (venue, pool ID), persist candidate provenance, and periodically refresh.
- API list endpoints may not provide immediate full coverage of launches; eventually combine listing, recently-created pool feeds, incremental cursors and on-chain program events. Never promise exhaustive or real-time coverage without measured evidence.
- **RPC upgrade later:** after implementation and credible opportunity research, upgrade to stronger RPC and add program-specific on-chain discovery, subscriptions/indexing and backfill. Reconcile API vs chain coverage and preserve the same verification gates. Do not block implementation waiting for that upgrade.

**Current implementation:** `arb/raydium_public_pool_discovery.py` lists Raydium AMM v4 pools without mint restrictions, with bounded pagination, liquidity filtering and program/mint checks; `arb/raydium_public_pool_candidates.py` supplies candidate IDs to `arb/eight_venue_onchain_probe.py`. The existing registry may contain manually curated **unverified candidates**, never a fixed discovery universe. The equivalent venue-wide API/index adapters for the other six active venues are future work; do not mark them complete. The read-only eight-venue probe can additionally ingest an untrusted Orca Token Swap v1 candidate-address JSON file (`--public-orca-legacy-candidates`) from a suitable index. The venue-wide GeckoTerminal adapter (`arb/orca_legacy_public_index.py`) can enumerate a selected Solana DEX's pools without token filters, with USD-reserve screening. **GeckoTerminal DEX labels are not a protocol-v1 guarantee**: CI now defaults to GeckoTerminal's observed Solana DEX catalog ID `orca` (confirmed in Surfpool CI #1836), with optional `ORCA_LEGACY_GECKO_DEX_ID` override. This enumerates **Orca-labeled** pools across tokens; the label does **not** establish Token Swap v1 ownership and results may predominantly be Whirlpool pools. The local-fork owner check against `DjVE6JNiYqPL2QXyCUUh8rNjHrbz9hXHNYt99MQ59qw1` is mandatory before counting a candidate. A configured index feed improves discovery but cannot guarantee v1 pools exist or are included. CI #1842 subsequently confirmed the indexed Orca cohort returned **16 untrusted candidates** and **all 16 had non-v1 on-chain program owners** (0 missing, 0 matching v1); read-only decoder verification remained **7/8**. The index adapter now supports a configurable broader cohort (up to 64 by default, up to eight index pages), and owner preflight reads accounts in batches of at most 16 before the full legacy verifier; these broader settings are not yet confirmed by a CI artifact. The subsequent `arb/orca_legacy_owner_preflight.py` batches account-owner reads against the **local Surfpool fork** and passes only exact Token Swap v1-owned accounts onward to the full decoder/vault verifier. Its JSON artifact distinguishes missing accounts, mismatched owners, and matching program owners. Program ownership alone is **not** a verified pool decoder or signed execution. Any selected pool still must match the **Orca Token Swap v1 program owner** on the local fork. An authenticated v1 pool is **not yet available**. Orca's archived legacy SDK is a potentially useful historical hint, **not** evidence of fresh/live pool listings. Do not conflate Orca Whirlpool listings with Orca Token Swap v1. No fresh Orca v1 pool is verified by this input capability alone.

## 4. Standalone venue acceptance gates (each of 8)

For every venue, separately demonstrate and retain evidence for:

1. **Decoder implemented:** decode authentic pool bytes with strict length, discriminator/layout, owner, version and protocol-specific invariant checks; unit tests include malformed accounts.
2. **On-chain pool authenticated:** real program-owned pool, valid mints, vaults, authorities, token-program variants, reserves and required companion accounts verified from Surfpool-fork RPC at a documented slot. Public API listing alone is insufficient.
3. **Swap builder implemented:** construct the correct program ID, ordered accounts, writable/signer flags, direction, amount mode, slippage/min-output constraints and remaining accounts. Unit-test serialized instruction bytes.
4. **Signed standalone execution verified:** build a transaction, sign **for local simulation only**, call `simulateTransaction` on Surfpool, prove expected program invocation and successful transaction, inspect pre/post token account balances and verify input decrease and output increase in correct token mints. Require nonzero meaningful deltas, proper account ownership, expected fees and failure diagnostics.
5. **Negative controls:** wrong owner, wrong mint, invalid authority, insufficient balance, malformed account/amount, missing required tick/bin/market accounts, slippage failure or similar applicable conditions fail closed. Never infer success from a builder importing or a transaction merely compiling.

Historical isolated evidence must be labeled historical and cannot be silently promoted to **current CI run** execution proof. Retain a per-venue JSON evidence record with status and reasons, artifact name, pool/slot, program, signed simulation success/error, token deltas and safety flags.

## 5. Cross-venue atomic acceptance (56 ordered combinations)

An atomic test is **two swap instructions in one signed transaction**: venue A swaps X→Y, then venue B consumes **that same intermediate Y** and swaps Y→Z. X and Z may be different. **Do not require a closed cycle** (X=Z) to pass the atomic execution test; cycles and profitability are separate later studies.

For all 8 venues, there are **28 unordered pairs and 56 ordered A→B combinations**. Each order is a separate gate: success for A→B does not prove B→A. Start testing ready venue pairs immediately; no need to wait for all eight.

For each order:
- Select authenticated pools with a genuinely shared intermediate mint Y and compatible token programs/accounts; do not assume every pair has a suitable route at a given time. Record **NO_ROUTE** separately from implementation failure.
- Build both instructions with compatible intermediate token account, amounts, min-outs and required signers/compute budget, preserving instruction order and atomic transaction boundaries.
- Run **one signed local-fork simulation**, verify transaction success, invocation traces, instruction order, X input and Z output deltas, and **intra-transaction continuity**: the first swap actually produces Y that the second consumes. Merely observing the two programs in logs or net-zero Y after simulation does not establish that continuity; use instruction-level token balance traces or another defensible proof.
- Test a forced failure of the second leg and verify **transaction rollback** (no first-leg state committed). A failed transaction alone does not prove rollback without appropriate state/balance evidence.
- Report route, two program IDs, pool IDs, mints X/Y/Z, slot, signed transaction simulation result, ordered instructions, token deltas, continuity proof, rollback evidence and artifact link.
- Distinguish **not tested**, **no compatible route**, **simulation failed**, and **verified**. Do not count an unordered historical pairing as proof of both orders.

`arb/cross_venue_atomic_simulation.py` currently has explicit false flags for intermediate consumption, order and rollback; these must remain false until independently demonstrated. `arb/execution_target_matrix.py` must continue to report the 56-order target honestly.

## 6. Evidence, CI and truthful status

CI must test decoder/builder units, discovery pagination and filters, API failure modes, wrong-owner/wrong-mint negative controls, local-fork authentication, signed standalone swaps, ordered atomic success, and second-leg rollback as these become implemented. Upload JSON artifacts **even when RPC errors prevent verification**; the eight-venue probe, JSON schema/safety-flag validation and evidence upload must be mandatory so green CI cannot mask failed generation or a missing artifact. Distinguish an infrastructure/rate-limit failure from a protocol failure.

As of 2026-10-23, Surfpool CI run **#1819** (commit `5ccd848`) produced an inspected artifact showing **7/8 on-chain decoder validations**, **8/8 builder modules detected**, and **0 newly signed-builder executions verified by that read-only probe**. Raydium AMM v4 was authenticated using API-discovered candidates; Orca Token Swap v1 was the single pending on-chain decoder (0 candidate pools in the artifact). Historical signed-swap and pairwise evidence exists but is not interchangeable with current-run proof. This snapshot is not live status; inspect the latest workflow, step logs and artifacts before updating it.

Capability registries such as `arb/venue_capabilities.py` and `arb/onchain_pool_discovery.py` may not yet enumerate all eight implemented adapters; reconcile registries and actual modules with explicit evidence levels rather than silently inflating readiness counts. The execution target matrix now independently inventories all eight decoder and builder modules (8/8 each) while keeping historical signed evidence separate and **current-run signed execution 0** until proved; the older `SWAP_BUILDERS` capability set intentionally remains scoped to historically integrated runners. CI #1846 indexed **19 Orca-labeled pools**, all 19 had owners other than Orca Token Swap v1; widening the same catalog is not guaranteed to resolve the legacy protocol gap. The owner-preflight artifact now includes per-program ownership counts to identify which programs dominate the public index.

**Builder validation improvement (2026-10-23):** the pairwise capability audit now installs `solders==0.26.0` so real instruction serialization tests are not silently skipped due to missing runtime dependencies. PumpSwap's local signed simulation post-state verifier also requires received output to meet the exact minimum-output threshold passed to the builder, in addition to signature verification, invocation and positive token deltas. These are **test and verification harness improvements**, not new successful standalone signed swap execution evidence. Confirm the latest CI run before treating its tests as passed.

**Signed-runner wiring regression (2026-10-23):** `tests/test_pumpswap_signed_runner.py` now exercises real `solders` transaction signing/serialization with mocked pool preflight, instruction construction and RPC simulation, checks forwarding of the minimum-output threshold to the post-state verifier, and asserts that unverified pools fail before signing. CI now runs this test. This is **unit-level wiring evidence only**: mocked simulation must never be counted as a successfully simulated real PumpSwap swap. The runner explicitly returns `actionable=false`, `live_execution_approved=false`, and `broadcast=false`.

**Signed atomic instruction preflight (2026-10-23):** `arb/signed_atomic_instruction_preflight.py` now inspects the actual serialized, signed legacy Solana transaction to prove the two specified venue program instructions occur in order, exactly once, and both reference the same candidate intermediate token account. Its isolated tests include reversed order, duplicate venue instructions, absent shared account, malformed bytes, and wrong program. This is **structural transaction evidence only**, not proof the first leg produces intermediate tokens, the second leg consumes them, either leg executes on Surfpool, or failed second-leg rollback. It is now wired into `verify_signed_atomic`, which calls `Transaction.verify()` on the serialized legacy signed bytes and requires the two venue instructions to share the supplied intermediate account. The verifier may mark **only** `instruction_order_verified=true` after structural validation and successful simulation logs/post-state, while `signed_atomic_simulation_verified`, `intermediate_intra_transaction_consumption_verified`, and `rollback_failure_case_verified` remain false. Unit tests include a tampered-signature rejection and a mocked RPC success response; **mocked responses never establish real fork execution**. Any address-lookup-table v0 transaction requires separate resolved-key handling before it can be trusted.

**DAMM v2 pre-signing reauthentication:** The runner now calls `arb/damm_v2_signed_preflight.authenticate_pool` against the local Surfpool fork immediately before signing. It rejects caller-supplied evidence that lacks a pool identity/slot/mint match, checks the current pool account's program owner and decoded state against the builder input, re-verifies synchronized vaults and checks non-stale evidence slots. A successful unit test of this guard is **not** proof of actual signed swap execution. The post-state simulator remains the authoritative signed-execution gate.

**DAMM v2 standalone signed runner (2026-10-23):** `arb/meteora_damm_v2_signed_runner.py` now requires onchain-authenticated DAMM v2 pool evidence, performs user-token mint/authority/balance preflight, builds and signs the exact-input swap2 instruction, then calls a generic local-fork `simulateTransaction` verifier. `arb/signed_standalone_swap_verifier.py` cryptographically verifies the serialized signature, one specified venue instruction **referencing both user input and output accounts**, program invocation and success, and actual two-account SPL token balance deltas meeting max-input/min-output. Negative tests cover forged signatures, wrong programs, insufficient output, remote RPC, and unauthenticated DAMM pools. These are **code paths and mocked-RPC unit tests**: no DAMM v2 real signed swap result is claimed until a successful authenticated Surfpool simulation artifact is produced.

**Standalone signed-instruction strictness (2026-10-23):** the SPL standalone post-state verifier now rejects any signed transaction containing more than the single explicitly selected venue instruction, or where either user token account is not writable. This prevents unrelated signed operations from being counted as a standalone swap proof. A new DAMM v2 runner test runs its actual `build_swap2` function and cryptographically verifies a signed serialized 14-account instruction with the expected discriminator, input and minimum-output amounts. The RPC simulation is still mocked; these tests do **not** prove a successful real DAMM v2 swap. Future legitimate compute-budget/setup instructions require an audited explicit allowlist rather than weakening this guard.

## 7. Milestones and order of work

**M1 — Discovery coverage.** Complete venue-wide, mint-agnostic, bounded API/index discovery for all eight venues where available; normalize candidates, liquidity/recent-pool queues, provenance, deduplication, refresh and failure handling. Public API discovery is allowed immediately. Document any venue without a suitable listing feed.

**M2 — Authenticate all eight.** Verify real pools and companion accounts in the local fork, including Raydium AMM v4 and Orca Token Swap v1. Prefer direct pool lookups from API IDs over program-wide scans. Do not confuse no candidate with no protocol.

**M3 — Eight standalone swaps.** Verify each decoder + builder + **signed execution** with token deltas and negative controls. Build missing execution harnesses and account fixtures. Start with available authentic pools; M2 and M3 can progress concurrently by venue.

**M4 — Ordered atomic verification.** For every available route among 56 ordered pairs, prove X→Y→Z in one signed simulation, instruction order, intermediate token continuity, output deltas and rollback. Track missing routes separately and continue expanding candidate coverage until each order has verifiable evidence or a documented blocking reason.

**M5 — Opportunity research, not execution.** Once implementations work, study token-agnostic cross-venue quote coverage, pool liquidity/depth, fees, slippage, compute cost, stale data, price impact and net expected value. No simulated opportunity implies a profitable executable trade. Do not require profitability for M2–M4 acceptance.

**M6 — Stronger RPC / production-quality discovery (deferred).** After implementation and opportunity research, adopt upgraded RPC, exhaustive filtered on-chain discovery, incremental pool-event indexing, freshness/latency measurements, API reconciliation, reliability and performance controls. Any subsequent live-trading capability would require a new explicit user decision and independent risk/security milestones.

## 8. Agent handoff and documentation rules

On every substantial change: update this roadmap if direction/acceptance changes; add focused tests and CI coverage; commit actual changes; provide branch, SHA, run ID, artifact, verified/unverified gates and blockers. Avoid hardcoded token pair constraints in new discovery adapters. Preserve safety flags and simulation-only operation. Prefer incremental verified progress over broad unsupported claims.

**Known implementation caveats to revisit:** confirm Raydium API list response shape and pagination with observed payloads; verify legacy AMM market PDA/nonce and OpenBook layout against real accounts; verify Orca Token Swap v1 layout and active pool availability; inspect CI step-level failures despite overall success; ensure cross-venue proof goes beyond terminal balances and invocation logs. Do not silently change status flags to make reports green.
