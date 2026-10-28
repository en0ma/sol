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
state using the existing `pumpswap_pool.verify` implementation. It captures
the pool bytes and reports the fee-mode diagnostic; it explicitly marks
native pricing, signed parity and admission false. Different RPC reads have
independent slots and are **not** misrepresented as one atomic snapshot.
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

## Requirements before claiming the fourth venue works

1. Implement exact official SDK-equivalent fee selection by quote mint and
   pool flags; revalidate the current fee-config account and creator override.
2. Implement exact base-unit buy/sell math including independent ceil-rounded
   fee components, signed virtual reserve and V2 accrued fee buckets. Cross
   check against the official SDK on identical snapshots. Do not rely on the
   indicative `pumpswap_quote` function as the signing floor.
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
