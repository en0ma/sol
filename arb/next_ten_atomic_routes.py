"""Next ten distinct ordered venue integration targets; zero implicit execution credit.

This is a prioritized route inventory, not genuine fork proof. Every
new pair requires its own authenticated source fixture, signed transaction,
SPL CPI continuity, fail-at-second control and independent acceptance.
"""
from arb.execution_target_matrix import TARGET_VENUES

BATCH_10=(
    ("meteora_damm_v2","orca"),
    ("orca","meteora_damm_v2"),
    ("raydium_cpmm","orca"),
    ("orca","raydium_cpmm"),
    ("meteora_damm_v2","meteora_dlmm"),
    ("meteora_dlmm","meteora_damm_v2"),
    ("raydium_cpmm","meteora_dlmm"),
    ("meteora_dlmm","raydium_cpmm"),
    ("meteora_damm_v2","pumpswap"),
    ("pumpswap","meteora_damm_v2"),
)
assert len(BATCH_10)==10 and len(set(BATCH_10))==10
assert all(a in TARGET_VENUES and b in TARGET_VENUES and a!=b
           for a,b in BATCH_10)

# Eight previously unattempted ordered venue pairs, plus both PumpSwap/DAMM
# retry controls. The latter are deliberately NOT new coverage identities.
NEXT_10=(
    ("orca","meteora_dlmm"),("meteora_dlmm","orca"),
    ("orca","pumpswap"),("pumpswap","orca"),
    ("raydium_cpmm","pumpswap"),("pumpswap","raydium_cpmm"),
    ("meteora_dlmm","pumpswap"),("pumpswap","meteora_dlmm"),
    ("meteora_damm_v2","pumpswap"),("pumpswap","meteora_damm_v2"),
)
assert len(NEXT_10)==10 and len(set(NEXT_10))==10
assert len(set(NEXT_10)-set(BATCH_10))==8
def route_batch(name):
    if name=="first":return BATCH_10
    if name=="next":return NEXT_10
    if name=="all":return ALL_42
    if name=="non-v4":return NON_V4_30
    if name=="remaining":return REMAINING_42
    raise ValueError("unknown atomic route batch")

# Exhaustive ordered seven-venue inventory for future sharded fork execution.
# Existing batch receipts are retained; an inventory never implies proof.
from itertools import permutations
ALL_42=tuple(permutations(TARGET_VENUES,2))
assert len(ALL_42)==42 and len(set(ALL_42))==42
REMAINING_42=tuple(pair for pair in ALL_42 if pair not in set(BATCH_10)|set(NEXT_10))
assert len(REMAINING_42)==24

def pair_shards(*,batch="remaining",shards=4):
    """Stable disjoint deterministic directed route worklists for separate forks."""
    if type(shards) is not int or not 1<=shards<=42:
        raise ValueError("invalid route shard count")
    routes=route_batch(batch)
    return tuple(tuple(route for i,route in enumerate(routes) if i%shards==shard)
                 for shard in range(shards))

NON_V4_30=tuple(pair for pair in ALL_42 if "raydium_amm_v4" not in pair)
assert len(NON_V4_30)==30 and len(set(NON_V4_30))==30
