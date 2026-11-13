# Native-pricing venue acceptance contract

## Scope and ownership

Current native-priced venues: Orca Whirlpool (`orca`), Meteora DAMM v2
(`meteora_damm_v2`), and Raydium CPMM (`raydium_cpmm`).

The next venue is **not yet selected or implemented**. Adding it must reuse
`arb/atomic_graph_coordinator.py`, `arb/venue_swap_adapter.py`, and the
existing persistent pool registry. Do not create a parallel coordinator, route
engine, registry, transaction broadcaster, or generic execution runner.

A venue owns its pool decoder, swap-account resolver, fee and exact integer
quote logic, official reference comparison, and instruction builder.
Cross-venue code owns graph composition, bounded selection, admission policy,
isolated trial orchestration, and independent acceptance.

## Fail-closed lifecycle per venue

1. **Discovery (manual / initial enablement).** Obtain a few untrusted addresses
   using the venue's existing discovery source; do not depend on continuous
   market crawling in pull-request CI.
2. **On-chain authentication.** Confirm owner/program, executable flags,
   pool layout and identity, mint and vault identities, configuration/fee
   account ownership, and venue-required auxiliary accounts. Reject unsupported
   native fee configurations. Record an observed RPC context slot where
   possible and never claim unrelated reads were atomic.
3. **Source capture.** Persist genuine program, pool, vault, configuration and
   auxiliary account bytes and identities for reproducible isolated tests.
   Missing tick arrays, observations, fee data, or program binaries fail closed;
   never fabricate inputs or silently use an indicative quote.
4. **Native exact-in pricing.** Return integer base units from the venue's
   native implementation, with explicit token direction and input. Independently
   compare to the official Core/SDK implementation where available.
5. **Signed isolated parity.** For each qualifying pool run **four actual signed
   swap simulations**: two directions and two *different* positive input sizes.
   Check executed program, observed SPL output, successful exact-input debit,
   stable fork clock when required, and agreement of native, official (where
   available), and signed integer outputs. Only local, isolated Surfpool;
   never broadcast to live network.
6. **Admission.** `promote_signed` must validate authenticated identity,
   all required venue receipt statuses, four distinct exact trials, and signed
   transaction evidence before admitting. A summary flag or `exact: 4`
   alone never establishes proof. Signed proof **must** be independently
   validated upstream; a digest-shaped string alone is not cryptographic
   verification. Recorded identity hints are not admission certificates.
7. **Coordinator.** One venue-specific swap adapter connects the native
   implementation to the existing coordinator. Revalidate *current* on-chain
   accounts before using a pool for a route; never infer present liquidity or
   current safety from historical signing.

## CI responsibilities

- **Fast:** Decoder/fee-quote boundary tests, signed receipt adversarial tests,
  adapter/coordinator integration and fail-closed behavior. All three venue
  authentication/capture/signed stage names remain separately visible.
- **Focused signed regression:** Reauthenticate a small known set of pools and
  capture current source accounts. Perform real signed parity on all three
  venues, enforce admission and independent receipt audit. Do not require
  six *previously unknown* pools on every pull request.
- **Discovery and multi-hop research:** Separate, explicit research workflows;
  not a prerequisite for the three-venue native-pricing milestone.

`arb/pool_registry.json` currently holds both historical identity hints and
entries validated in earlier runs; entries do **not** store a durable,
independently authenticated signed-admission certificate. It must **not** be
interpreted as an allowlist of proven tradable pools without the current-run
signed evidence and on-chain revalidation. The future durable provenance
feature needs an independent receipt integrity scheme and an explicit
eligibility filter, with tests for legacy entries.

## Checklist before implementing venue 4

- Identify the target program IDs, official Core/SDK or an independent
  reference, native account layouts, fee schedule and token-program support.
- Verify existing on-chain decoder, discovery, swap builder and adapter reuse
  opportunities before writing new code.
- Document exact signed simulation account prerequisites and expected
  unsigned-to-signed transaction boundary.
- Build venue-only authentication, source-capture and native-pricing fixtures;
  then four-direction/size signed parity trials on isolated Surfpool.
- Extend shared admission with the new venue's receipt schema **without**
  weakening any of the existing three-venue evidence requirements. Generalize
  the current three-venue-specific validator only once the fourth venue's
  independent source proof is established.
- Add adapter and coordinator integration tests. Require no broadcast,
  no silent stages, no reuse of old receipts as new signing, and independent
  audit of every promoted identity.
- Obtain a fully green focused CI with real native/signed agreement before
  claiming the fourth venue is supported.

Do not begin continuous discovery, profitability claims, or live execution
as part of fourth-venue native-price enablement.
