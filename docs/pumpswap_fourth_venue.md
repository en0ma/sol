# Venue 4: PumpSwap native-pricing research and implementation

**Selected venue:** PumpSwap AMM, program
`pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`.

**Acceptance status: NOT YET SIGNED-VERIFIED.** This is a staged fourth-venue
implementation; no claim of executable native price parity or registry admission.

## Why this venue and what already exists

The repository already contains the strict `pumpswap_pool` decoder/verifier,
canonical pool classification, `pumpswap_fee_account` authentication, fee tier
and fee-mode diagnostic code, V2 exact-input instruction builders,
`pumpswap_local_simulation`, an existing `pumpswap` route adapter, and ten
registry identity hints. Reuse these. Do not build another coordinator or
swap runner. The existing `pumpswap_quote.quote_exact_input` explicitly
returns `INDICATIVE_PUMPSWAP_ONLY` and must never be promoted into an
executable quote based on a fabricated fee-rate input.

## Official references reviewed (October 2026)

- Pump official documentation, PumpSwap V2 trades:
  https://github.com/pump-fun/pump-public-docs/blob/main/docs/instructions/PUMP_SWAP_TRADE_V2.md
- Official `@pump-fun/pump-swap-sdk`: https://www.npmjs.com/package/@pump-fun/pump-swap-sdk
- Published SDK source mirror: https://github.com/nirholas/pump-swap-sdk
- Existing project source: `arb/pumpswap_pool.py`,
  `arb/pumpswap_fee_modes.py`, `arb/pumpswap_quote.py`,
  `arb/pumpswap_trade_v2.py`.

The V2 `buy_exact_quote_in_v2` and `sell_v2` instructions price the same
as V1, but handle protocol/creator fee payout differently. A cashback pool
cannot use V2. Fee schedule selection depends on canonical classification,
quote mint (SOL-like, stable, other), market-cap tier, configurable creator
fee and possible Mayhem mode. **Individual fee components round upward**, so
a total PPM fee deducted once before CPMM division is not sufficient proof.
The effective quote reserve is **physical quote vault plus a signed i128
virtual reserve**; physical spendable quote liquidity excludes separately
accrued protocol/creator buckets. Signed virtual reserves may be negative.
Fee buckets may be present in the vault and must not be misinterpreted as
spendable sell liquidity.

These are behaviors grounded in the referenced October 2026 docs/SDK, not
proof that the current repository's Python math exactly matches the program.

## Implemented in this stage

`arb/pumpswap_native_source_capture.py` takes a bounded sample of
already-registered identity hints and independently verifies pool owner,
layout, mint identity, vaults, fee/configuration accounts and current on-chain
state using the existing `pumpswap_pool.verify` implementation. It captures the verified same-slot six-account bundle (pool, both vaults,
global config, fee config, base mint), the pool account bytes, the fee-mode diagnostic, and four clearly unverified
candidate exact-input quotes (two directions × two sizes); it explicitly marks
native pricing, signed parity and admission false. The independently retrieved initial pool account and verifier snapshot have
separate slots; only the six verifier-snapshot accounts share a context slot.
The report preserves both slot values rather than misrepresenting them as one
atomic read.
The CLI exits nonzero when the requested sample is incomplete. No DEX API,
market scan, sendTransaction or local signing is used by this source step.

Example, using an independently supplied read-only upstream RPC URL:

```bash
python3 -m arb.pumpswap_native_source_capture \
  --rpc "$SOLANA_RPC_URL" \
  --registry arb/pool_registry.json \
  --limit 3 \
  --output pumpswap-native-source-research.json
```

Also added `arb/pumpswap_native_candidate.py`, a strict, integer-only Python translation of the SDK’s quoted-input buy and base-input sell formulas, including per-component ceil-rounded fees, the signed virtual quote reserve, market-cap tiers, stable/noncanonical/Mayhem fee selection and V2 accrued fee buckets. It returns `UNVERIFIED_NATIVE_FORMULA_CANDIDATE`, never an executable native quote. A dedicated regression test covers these calculations, invalid account state, and fee-schedule selection. Its output still requires comparison to the actual upstream SDK on authenticated snapshots and four genuine signed swaps per pool.

A separate manual-only workflow, `.github/workflows/pumpswap-fourth-venue-source.yml`, runs the bounded source capture using the existing upstream RPC secret. It cannot claim signed parity or admit pools.

## Independent published SDK candidate-price gate

`tools/pumpswap_sdk_oracle.js` imports the pinned published
`@pump-fun/pump-swap-sdk@2.2.0` and decodes the authenticated source bytes
using `PUMP_AMM_SDK`. It independently calls the SDK's
`buyQuoteInput` and `sellBaseInput` with the same reserves, fee
config, actual quote mint, Mayhem flag, virtual reserve, creator rate
and outstanding fee buckets. It compares four outputs to Python's
candidate calculations; `arb/pumpswap_sdk_candidate_audit.py` rejects
missing trials, mismatched outputs, duplicate sizes/directions, incorrect
source pool identities and any claim that SDK equivalence establishes
signed execution.

The independent Python audit additionally binds each official SDK trial to the corresponding untouched authenticated source-candidate amount, mint direction, and output. Comparing two self-consistent but forged SDK report fields is insufficient; mismatch with the original source candidate fails closed.

The **manual** `PumpSwap Fourth-Venue Source Research` workflow now
runs source authentication, official SDK candidate comparison, then
independent candidate audit, and uploads all reports. This is a
*fail-closed experimental gate*, not a green certified fourth venue.
Running that workflow against fresh upstream state and inspecting its
receipt is still necessary; routine focused CI only runs the offline
adversarial tests. GitHub may require the workflow file on its default
branch before offering manual dispatch.

## Requirements before claiming the fourth venue works

1. Independently compare every candidate exact-base-unit buy/sell formula
   against the *actual* official SDK on identical authenticated snapshots,
   including nonzero creator override, cashier/cashback, token programs,
   Mayhem fee modes and any program upgrades. Existing code rejects creator
   overrides rather than inventing the unavailable GlobalConfig gate.
   Do not rely on the indicative `pumpswap_quote` function as a signing floor.
2. Extend genuine source capture to include the official SDK auxiliary
   accounts and signed swap prerequisites at an audited consistent context.
3. Sign and simulate V2 exact-input buy and sell on an isolated Surfpool with
   authenticated accounts and a verified eligible buyback recipient ATA.
   Reject cashback pools for this V2 path. Verify observed SPL debits and
   credits, instruction success, and exactly matching integer native quote.
4. Run **two directions × two distinct input sizes** per pool; independently
   audit each signed transaction proof and receipt, and persist provenance
   before extending the shared `promote_signed` admission validator.
5. Revalidate admitted pool state again before coordinator use. Old registry
   identities cannot bypass admission or replace fresh source evidence.

This stage deliberately has **no broad-market discovery**, no fake signed
receipts, no bypass of unsupported fee modes, and no live broadcasting.
