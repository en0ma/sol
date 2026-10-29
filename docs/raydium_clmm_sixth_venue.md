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
