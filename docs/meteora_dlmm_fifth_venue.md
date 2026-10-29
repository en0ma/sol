# Fifth native venue: Meteora DLMM (research/acceptance entry point)

**Chosen next venue:** `meteora_dlmm` / Meteora Liquidity Book, program
`LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo`. The tracked registry
already has six DLMM identity hints. This reuses existing
`arb/meteora_dlmm.py`, `arb/meteora_dlmm_bin_preflight.py`,
`arb/meteora_dlmm_swap.py`, `arb/venue_swap_adapter.py`, and the one
`arb/atomic_graph_coordinator.py`—no competing graph engine or discovery.

## What is actually implemented

`arb/meteora_dlmm_fifth_venue_source.py` is a read-only, bounded,
registry-hint-only source capture. It checks the 904-byte LbPair owner,
status and mint identities, then obtains the same-slot pool, two SPL
reserves, oracle, active and adjacent bin arrays, and two classic SPL
mints. It validates each bin-array PDA's index, parent, discriminator
and program ownership; the oracle observation bounds; and both reserve
mints and common authority. It retains exact original account bytes,
lamports, slot and deterministic SHA-256 provenance. Missing optional
neighbor arrays are explicitly absent; missing active array is fatal.
The snapshot is **not** a price quote or a signed receipt; the downstream signed acceptance job is the execution proof.

CLI example (read-only RPC):
```bash
python3 -m arb.meteora_dlmm_fifth_venue_source \
  --rpc "$SURFPOOL_DATASOURCE_RPC_URL" \
  --registry arb/pool_registry.json \
  --count 3 \
  --output dlmm-authenticated-source.json
```

## Pricing reference and next acceptance steps

Meteora's maintained SDK exposes `getBinArrayForSwap` and
`swapQuote(inAmount, swapForY, allowedSlippage, binArrays)`. For
`swapForY=true`, the input is token X and the output is token Y.
Quotes return **integer** `consumedInAmount`, `outAmount`, fee and
protocol fee, and the precise bin-array path. Variable fee updates,
bitmap extension, per-bin liquidity, partial fills, activation rules
and the fork Clock all matter. In particular, pool-wide vault reserves
cannot reproduce exact DLMM prices.

References:
- https://github.com/MeteoraAg/docs/blob/main/developer-guides/dlmm/typescript-sdk/reference.mdx
- https://github.com/MeteoraAg/docs/blob/main/developer-guides/dlmm/rust-integration/library.mdx
- https://github.com/MeteoraAg/dlmm-sdk

## First completed three-pool signed acceptance

The **real three-pool** isolated execution at
https://github.com/en0ma/sol/actions/runs/40819813329 passed source, the
published `@meteora-ag/dlmm@1.9.14` SDK, a separate integer bin-walk
(`meteora-dlmm==0.5.0`) at the authenticated Clock timestamp, and
**12 actual Ed25519-signed legacy DLMM program simulations** (two
directions × two sizes per pool). Independent post-hoc audit rechecked
signed wire bytes and program id/role/amount, raw SPL user debit/credit,
source identities, output parity and distinct signatures.

The three existing registry hints promoted from this evidence are:

- `5rCf1DM8LjKTw4YqhnoLcngyZYeNnQqztScTogYHAS6`
- `BGm1tav58oGcsQJehL9WXBFXF7D27vZsKefj4xJKD5Y`
- `6oQ9wVex4mKZti2GsGCfD8FWTMMC9PLQkztRU5cd6MK8`

`arb/meteora_dlmm_signed_registry_merge.py` re-runs the complete audit
and only annotates existing identities with immutable source digest,
slot, exact signed-transaction hashes and independent receipt digest.
No new coordinator or venue registry was introduced. Neither these
receipts nor unit tests authorize live broadcasting.

**Remaining**: Three more tracked DLMM pools have not yet demonstrated
signed parity. Pools requiring an extended bitmap path, special
limit-order liquidity, Token-2022 hooks or multiple additional bin
arrays need expanded source hydration and refreshed signed evidence.
Independent exact outputs on the three accepted pools do not prove
all DLMM modes.

## PumpSwap handoff before fifth venue

The separate genuine PumpSwap seven-pool workflow successfully accepted
**six additional pools**, reaching **seven distinct independently audited
signed pools** in `arb/pool_registry.json` with durable signed
provenance and a seven-pool evidence artifact.

Evidence: https://github.com/en0ma/sol/actions/runs/40813671557
