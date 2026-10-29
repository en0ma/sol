# Meteora DBC six-pool continuation checkpoint — 2026-10-29

## Evidence rule

The requested seventh-venue target is **six distinct original DBC pools with
four genuine signed isolated Surfpool swaps per pool (24 transactions)**,
independent native/official SDK exact integer parity, independent Ed25519
and SPL debit/credit audit, and signed-qualified evidence in the **existing**
`arb/pool_registry.json`. This target is **NOT yet achieved**. Do not
promote candidate source or signed diagnostics as accepted registry pools.

No mainnet broadcasts or account writes are permitted. Use original mainnet
source accounts read-only and simulate only against isolated Surfpool.

## Confirmed starting evidence

- Original DBC program ELF authenticated, but program-account scans throttled.
- [First successfully authenticated original DBC pool + SDK quotes
  run](https://github.com/en0ma/sol/actions/runs/40900194890):
  independently authenticated **one** original on-chain VirtualPool with
  PoolConfig/vaults/Clock, and four nonzero official pinned SDK exact-in quotes.
  [Artifact 12907694995](https://github.com/en0ma/sol/actions/runs/40900194890/artifacts/12907694995).
- [Second distinct original source candidate
  run](https://github.com/en0ma/sol/actions/runs/40908174752):
  captured original source + SDK quotes on a distinct two-point curve,
  but the then-current native *single-segment* audit failed. That failure
  was an intentional unsupported-mode rejection, not signed parity.
  [Artifact 12911659087](https://github.com/en0ma/sol/actions/runs/40908174752/artifacts/12911659087).
- [Six-pool source research
  run](https://github.com/en0ma/sol/actions/runs/40908544803):
  discovered six original program-owned candidate identities in a bounded
  256-transaction history, but only **three of six** passed contextual
  source screening. The strict six-source gate correctly failed. Rejections
  included migrated and unsupported original states. These three were not
  signed-qualified pools.

## Implementation in this development continuation

### Original account source, discovery and independent evidence
- `arb/meteora_dbc_seventh_recent_tx_discovery.py`: original-program
  transaction hints, paginated with explicit request/slot bounds;
  original owner and VirtualPool discriminator verification.
- `arb/meteora_dbc_seventh_candidate_capture.py`: individual source
  reauthentication; explicit strict vs partial diagnostic modes.
- `arb/meteora_dbc_seventh_state_capture.py`: original source pool,
  config, mint, vaults, Clock and static migration/ownership guards.
- `arb/meteora_dbc_seventh_source_audit.py`: independent saved-raw-byte
  identity, hash, owner and role audit.
- `arb/meteora_dbc_six_source_qualification.py`: exact six distinct
  independently verified pool target and explicit preservation of
  partial research evidence before a nonzero failure.
- `.github/workflows/meteora-dbc-six-source.yml`: bounded live six-source
  research and four SDK quotes per source, with raw artifacts even on
  incomplete target. A new run must be inspected before stating six passed.

### Source-native exact integer pricing
- `arb/meteora_dbc_native_segment.py`: genuine Q64 sqrt-price,
  Q128-denominator arithmetic with explicit integer rounding.
- `arb/meteora_dbc_native_curve_walk.py`: original full bounded
  liquidity-point traversal, both input directions, fail-closed partial fills.
- `arb/meteora_dbc_native_fee.py`: original packed PoolConfig
  static linear/exponential Q64 fee scheduling, raw Clock activation,
  direction-specific input/output fee modes and 20% protocol split.
  Dynamic fees, rate limiter, transfer fees, transfer hooks and
  unsupported fee modes are rejected.
- `arb/meteora_dbc_native_fee_parity.py`: independently compute
  exact-input, gross/native curve, input/output fees and next price
  from original bytes, then reconcile against pinned original DBC SDK.
  This is *source-native quote parity only* if/when its CI passes.
- `arb/meteora_dbc_native_curve_audit.py` preserves a separate
  curve-only proof boundary.

### Offline signed diagnostics, not acceptance
- `arb/meteora_dbc_swap.py`: original IDL `swap` instruction account
  order/discriminator with signer and SPL-only restrictions.
- `arb/meteora_dbc_signed_fork_research.py`: original ELF hydration,
  offline clock and source account restore, ephemeral user accounts,
  local Ed25519-signed four trial simulation research. Only accepts
  source-backed *full-fee* native/SDK quote parity as input. Its status is
  deliberately `DBC_SIGNED_OFFLINE_DIAGNOSTIC_NOT_ACCEPTED`.
- `.github/workflows/meteora-dbc-signed-research.yml`: installs
  isolated Surfpool, freezes it before source capture, runs source,
  official SDK and independent native math before any signed diagnostic;
  keeps diagnostic evidence and logs.

## Critical remaining six-pool acceptance gates

1. Actually collect **six** distinct, still-active independently
   authenticated original pools (not just six transaction-history hints);
   failures should preserve partial source artifacts without approval.
2. Achieve CI-backed **four exact full-fee native/SDK quotes per pool**,
   24 total on the same original bytes. All unsupported modes fail closed.
3. Achieve **24 real distinct Ed25519-signed offline Surfpool transactions**,
   independently reparse wire signatures, source accounts, raw user SPL
   pre/post states, fees and accepted outputs. A green diagnostic job alone
   does NOT satisfy this independent signed audit.
4. Promote only independently audited pool identities and all 24 hashes
   using the **existing** shared registry admission path, with no new
   coordinator and no mainnet broadcast.

## Seven venue acceptance report

| Venue | Established signed acceptance | New-format signed pools | Required change |
| --- | --- | ---: | --- |
| Orca Whirlpool | Yes, historical | Legacy provenance | Preserve |
| Meteora DAMM v2 | Yes, historical | Legacy provenance | Preserve |
| Raydium CPMM | Yes, historical | Legacy provenance | Preserve |
| PumpSwap | Yes | 7 | Preserve |
| Meteora DLMM | Yes | 6 | Preserve |
| Raydium CLMM | Yes, supported single-tick subset | 7 | Preserve |
| Meteora DBC | **Not yet** | **0 of 6** | Finish 24 signed audited swaps and registry promotion |

This is an implementation checkpoint, not a claim that CI has
completed every new job or that the seventh venue is fully accepted.
