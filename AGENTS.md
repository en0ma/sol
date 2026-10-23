# Sol — Agent operating instructions

Read this file and [docs/ROADMAP_AND_ARCHITECTURE.md](docs/ROADMAP_AND_ARCHITECTURE.md) before making changes. The roadmap is the durable record of user-agreed design directions and acceptance criteria. Update it whenever a design decision, target, or milestone changes.

## Non-negotiable safety boundary
This project is **simulation and verification only**. Do not send, sign-and-broadcast, or submit live/mainnet swaps, connect funded execution wallets, enable automated trading, or claim trading approval. Local-fork transaction signing solely for `simulateTransaction` is permitted. Keep `actionable=false`, `live_execution_approved=false`, and `broadcast=false` in execution/evidence outputs. Any eventual live execution is a separate future project phase requiring explicit user authorization and controls.

## Required working style
- Make actual code/test/CI changes when asked to proceed; commit to the working branch and report SHA and evidence. Do not report intentions as accomplishments.
- Distinguish **implemented**, **unit tested**, **on-chain authenticated**, **signed standalone simulated**, and **atomic execution verified**. A builder module or a green CI workflow does not prove successful execution.
- Preserve and cite evidence artifacts, fork slot, pool/program IDs, ordered instructions, token balance deltas, failure/rollback checks, and CI run ID. Never fabricate a passing result or upgrade verification flags without proof.
- Fail closed on missing accounts, stale API responses, mismatched program owners, unsupported layouts, RPC 429s, and unverified token/vault authority. Do not equate missing RPC evidence with venue absence.
- Prefer **venue-wide public API/index pool enumeration**, no hardcoded token pair or static pool-only universe. Apply configurable liquidity screening, classify by venue program, and authenticate candidates independently on-chain in Surfpool. APIs are discovery hints, never security or execution evidence. Add RPC-native exhaustive discovery later when the user upgrades RPC.
- Do not require a closed X→Y→X arbitrage cycle for the two-venue atomic acceptance test: X→Y on venue A then Y→Z on venue B is sufficient when token continuity and atomic execution are proved.
- Test **both execution directions** for each active venue pair (7 venues = 21 unordered, 42 ordered). Begin testing ready pairs without waiting for all seven venues. Orca Token Swap v1 is deprecated and archived as optional legacy code; do not make it an execution acceptance gate or run its legacy discovery in active CI.

## CI efficiency
- Deliver coherent multi-file batches, test locally first, and push once per batch to avoid repeated expensive Surfpool CI and cancellation.
- Keep deprecated Orca Token Swap v1 discovery out of mandatory CI while preserving its code and isolated tests.
- Prioritize actual local-fork signed execution and atomic rollback artifacts over narrow harness-only changes.

## Source of truth
- Roadmap: `docs/ROADMAP_AND_ARCHITECTURE.md`
- Active seven-venue target matrix: `arb/execution_target_matrix.py`
- Fork evidence: `arb/eight_venue_onchain_probe.py` and GitHub Actions artifacts
- Discovery: `arb/raydium_public_pool_discovery.py`, `arb/onchain_pool_discovery.py`
- Capability registries may lag actual builder modules; reconcile before claiming coverage.

## Before claiming a milestone
Inspect the **actual CI step and JSON artifact**, not only the overall workflow conclusion. Check negative controls, explicit signed swap simulation success, pre/post token balances, intermediate token flow, instruction order and atomic rollback. Document what remains unverified.
