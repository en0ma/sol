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
