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

## Further implementation in this pass (not a claimed six-pool acceptance)

The following **additional** fail-closed components were committed after
the original checkpoint text was created:

- `arb/meteora_dbc_native_curve_walk.py`: original Q64 multi-point
  integer curve traversal in both directions. It replaces the initial
  single-segment-only approximation in the independent curve and
  full-fee parity audits. The original source SDK evidence contains
  two-point curves, so refusing all multi-point pools was too restrictive.
- `arb/meteora_dbc_native_fee.py`: Q64 exponential-fee exponentiation
  updated to the source-matched binary rounding algorithm.
- `arb/meteora_dbc_swap.py`: original Anchor IDL `swap` discriminator,
  account metas, strict input/mint/source roles and offline-only flags.
- `arb/meteora_dbc_signed_fork_research.py`: diagnostic signed original
  ELF in isolated Surfpool, with original raw SPL poststates and signed
  wire bytes retained. **This file existing is not proof of a passed
  signed simulation.**
- `arb/meteora_dbc_signed_audit.py`: independent Ed25519-signed wire,
  instruction, 4-per-pool identity, token account and SPL poststate
  verifier. **Only actual accepted receipt artifacts can pass.**
- `arb/meteora_dbc_signed_registry_merge.py`: produces a candidate
  update to **the existing** shared registry only after the independent
  real signed auditor accepts each pool. No changes to the shared
  coordinator or live execution permissions.
- `.github/workflows/meteora-dbc-signed-research.yml`: supports a
  one-pool PR diagnostic or an explicit six-pool manual research path,
  requiring native/official SDK full-fee parity, signed offline
  execution, independent signed audit, and existing-registry artifact.
- Added independent fee, two-point curve, IDL wire, signed audit and
  registry fail-closed regression tests.

**Exact acceptance at this checkpoint remains DBC 0/6 signed pools,
0/24 independently audited signed trials.** New CI checks have been
pushed but their latest runs were still queued when last inspected;
there is no permission to infer acceptance from their creation.

To inspect current runs:
- [Six-source and 24 SDK/native quote workflow](https://github.com/en0ma/sol/actions/workflows/meteora-dbc-six-source.yml)
- [Original DBC signed offline research](https://github.com/en0ma/sol/actions/workflows/meteora-dbc-signed-research.yml)
- [Original single-source/sdk provenance](https://github.com/en0ma/sol/actions/workflows/meteora-dbc-seventh-candidates.yml)

CI now cancels superseded runs for these three DBC workflows to
reduce unnecessary queued work. No newer success is assumed.

## Verified later checkpoint: distinct historical signed executions

The earlier 0/24 statement above is obsolete as a *historical user-SPL
signed-evidence count*. Six separate, successful CI runs have now independently
audited one unique original DBC pool and four genuine Ed25519-signed offline
Surfpool swaps per run. These are **six distinct pool identities**, not one
six-pool synchronized execution:

| Original source pool | Signed CI run | Vault poststates in receipt |
| --- | --- | --- |
| `7aBcKp4oB3A4NHqRtDBUciv7X8NB7QJN3xemEdhMmfWY` | [40934682876](https://github.com/en0ma/sol/actions/runs/40934682876) | No |
| `SWYietXaV2dHysWiRxG9peLPCAmLj3awLdRfn2RMY6y` | [40951035859](https://github.com/en0ma/sol/actions/runs/40951035859) | No |
| `6ygQ1h9yUFnwNuKdx6KC717y2s3UbDFWAAsfaA4NQ71h` | [40954739110](https://github.com/en0ma/sol/actions/runs/40954739110) | No |
| `E4k5UbS5gidrL4hb1NJDLrjXKKzFRFDNYkACrn89mDZA` | [40957392652](https://github.com/en0ma/sol/actions/runs/40957392652) | No |
| `PjKcoXKDPCwjqA8T6sMRwasVNkz6pKNh5hxfs3yKM7U` | [40958792518](https://github.com/en0ma/sol/actions/runs/40958792518) | No |
| `Hx4wZyYwPLyVyVkui8JBDt8rWPhNXfzo3j9h3Kh6s6Cw` | [40962606945](https://github.com/en0ma/sol/actions/runs/40962606945) | **Yes, independently audited** |

Each run's downloadable `dbc-signed-offline-research-unaccepted`
artifact contains original source proof, official SDK and native parity,
signed transaction wire, independent signed audit, and conservative
non-broadcast flags. All six independent signed reports state
`signed_trials_verified: 4`; combined there are **24 historical
user-SPL signed trials across six distinct pools**.

**Do not interpret this as six-pool full vault-backed acceptance.**
The newer signed runner now includes the original base and quote vault
poststates returned by the genuine signature-verified simulation.
`arb/meteora_dbc_signed_audit.py` independently verifies source-vault
digests, SPL mint/authority, and exact input credit/output debit.
Only the last run captured those additional vault poststates; older
receipts cannot be retrospectively upgraded.

The current independent vault-accounting milestone is **1 of 6 pools,
4 of 24 trials**, while historical signed SPL verification is
**6 of 6 pools, 24 of 24 trials**. DBC registry admission under the
stronger Orca-equivalent standard remains **0 of 6**.

The original six-pool SDK/native regression is independently verified
at **6 sources / 24 quotes**, using immutable authentic October 29
snapshots. Pull-request CI intentionally reaudits the historical bytes,
since DBC launchpad curves migrate or drain rapidly. A manual live
research run must still reauthenticate current source accounts.
Surfpool `surfnet_timeTravel` cannot rewind to archived source times;
therefore archived unsigned snapshots cannot be replayed as historical
signed results without a separate, time-consistent fork runtime.
