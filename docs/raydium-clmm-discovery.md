# Raydium CLMM pool discovery

A third venue is now supported for **account decoding and mint-pair
discovery**: Raydium CLMM, `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK`.
It reads the 1544-byte packed PoolState with mint offsets 73 and 105,
and validates both SPL vault mint balances, authorities, and active liquidity.

Upstream source: https://github.com/raydium-io/raydium-clmm/blob/master/programs/amm/src/states/pool.rs

This is not an executable CLMM swap. Proper tick arrays, token program
selection and swap_v2 instruction simulation remain to be implemented.
Account scans can still get 429 responses even after exponential jitter.
