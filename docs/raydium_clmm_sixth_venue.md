# Sixth native-integer venue: Raydium CLMM

The sixth target is `raydium_clmm`, program
`CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK`.
This reuses the existing `arb/raydium_clmm.py`,
`arb/raydium_clmm_swap.py`, `arb/venue_swap_adapter.py`, and the
single `arb/atomic_graph_coordinator.py`; **no new coordinator** or
registry was created.

## First real authenticated source result

The sixth-venue source workflow completed successfully:
https://github.com/en0ma/sol/actions/runs/40849750678

- Registered pool: `61R1ndXxvsWXXkWSyNkCxnzwd3zUNB8Q2ibmkiLPC8ht`
- Source slot: `462830281`
- Bound source SHA-256:
  `0550d0ce2f0af2a8f992fb81809c7c642e88a7c6b91477228403beff5d356e01`
- Current tick: `4990`; tick spacing: `60`

`arb/raydium_clmm_sixth_venue_source.py` checks the real program-owned
1,544-byte PoolState and captures a synchronized same-slot snapshot
of the pool, two SPL token vaults, AMM configuration, observation
account and both mint accounts. It verifies program ownership,
the registered mint pair, common vault token authority and nonzero
reserves, stores original account bytes and lamports, and computes an
authenticated snapshot digest. It refuses all live execution and
signed registry promotion.

Run a fresh source capture:

```bash
python3 -m arb.raydium_clmm_sixth_venue_source \
  --rpc "$SOLANA_MAINNET_RPC_URL" \
  --registry arb/pool_registry.json \
  --count 1 \
  --output raydium-clmm-sixth-source.json
```

## Acceptance work still required

Raydium CLMM requires the authenticated tick-array bitmap and
ordered initialized tick-array state, pool fee mode, dynamic fees and
tick-crossing integer liquidity math. Aggregate vault reserves are **not**
sufficient for an exact CLMM quote. Subsequent acceptance must independently
match the official Raydium SDK against pure native integer price
calculations and execute four real signed isolated Surfpool swap_v2
transactions per pool (two directions, two sizes), with separate signed
SPL-output audit.

**Current stage: authenticated source only (one pool).**
Do not mistake the existing swap-v2 instruction builder or a green
source workflow for signed pricing parity, multi-venue atomic execution,
or any authorization to broadcast.

## Genuine tick-array liquidity snapshot achieved

The next step beyond the pool/vault snapshot is now implemented as
`arb/raydium_clmm_tick_source.py` and
`arb/raydium_clmm_sixth_tick_capture.py`. It derives the official
`tick_array` PDAs from the tracked pool and signed big-endian start
indices, captures bounded neighborhoods around the active tick in a
single `getMultipleAccounts` read, authenticates ownership, original
packed account bytes, discriminator, parent pool, start index and
initialized LP liquidity. The source preserves non-LP initialized
ticks separately rather than silently treating limit-order
liquidity as ordinary active LP reserves. A bounded retry tolerates
pool-price movement only when the authenticated pool+tick snapshot
is internally synchronized. The initial source and subsequent tick
snapshot retain **separate** slots and hashes: two RPC reads never
become a falsely claimed same-slot snapshot.

The completed source-plus-tick workflow is:
https://github.com/en0ma/sol/actions/runs/40857628564

This is an actual authenticated tick-array source milestone; it
is **not** the official Raydium SDK pricing comparison or signed execution
acceptance. The latter still requires correct CLMM dynamic fee, limit
order matching, tick-array bitmap traversal and four fresh signed
swap_v2 executions with independent SPL and SDK reconciliation.

## Sixth-venue genuine four-swap acceptance achieved

The first real CLMM fourth-trial execution and separate signed audit both
passed on the tracked RAY/USDC pool:

https://github.com/en0ma/sol/actions/runs/40862666749

This uses **two directions × two raw input sizes (10,000 and 100,000)**
at one authenticated same-slot PoolState/AmmConfig/vault/observation/mint/
tick-array snapshot. The independent Python Q64.64 single-tick integer
engine is compared to the official pinned
`@raydium-io/raydium-sdk-v2@0.2.75-alpha` output on exact same bytes.
The original Raydium CLMM upgradeable program ELF is hydrated to an
isolated offline Surfpool. Four distinct ephemeral Ed25519-signed real
`swap_v2` instructions invoke the genuine program; sig-verifying
Surfpool simulation returns exact SPL token account debit/credit and
success logs. The independent receipt verifier re-parses the signed
wire bytes, program/role/tick-array/amount/min-output, Ed25519
signatures, raw SPL poststate and reference quote identities.

**Four signed results in raw token base units:**

| Exact-input direction | Input | Exact SDK/native/observed output |
| --- | ---: | ---: |
| RAY → USDC | 10,000 | 16,535 |
| RAY → USDC | 100,000 | 165,354 |
| USDC → RAY | 10,000 | 6,017 |
| USDC → RAY | 100,000 | 60,174 |

Original signed-audit source slot: `462857973`.
Authenticated tick snapshot SHA-256:
`b8ccfd7880d5ab895ad8778f01c713407d5cc2137a714e420ee03910388a8f03`.
The independent audit status is
`INDEPENDENT_CLMM_SIGNED_NATIVE_SDK_SPL_PARITY` for one pool.
The existing signed pool registry contains the full original
four transaction hashes and independent receipt digest.

The scope is **deliberately restricted to single-tick swaps** with
source-confirmed zero dynamic fee and fee collection on input.
The integer engine rejects all tick-crossing candidates,
output-side fee variants and dynamic-fee pools. This is not proof
of arbitrary Raydium CLMM swaps or limit-order paths, and it
does not authorize live broadcasting. The official SDK returns a
tick-account path including prefetch accounts; authenticated source
membership is required for each.

Signed acceptance and source/SDK/native/SPL output artifact:
https://github.com/en0ma/sol/actions/runs/40862666749/artifacts/12892407092
