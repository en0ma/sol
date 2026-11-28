# Raydium CLMM swap_v2 instruction groundwork

`arb.raydium_clmm_swap` builds the Raydium CLMM `swap_v2` Anchor
instruction with the source-defined amount, threshold, sqrt price limit,
and exact-input/exact-output flag. The builder sets the 13 declared
accounts in program order plus explicitly supplied writable tick arrays.

Source: https://github.com/raydium-io/raydium-clmm/blob/master/programs/amm/src/instructions/swap_v2.rs

**Not execution verified:** CLMM tick-array selection and pool-specific
oracle and price preflight remain outstanding. This module cannot safely
be included in executable route selection until an actual local Surfpool
simulation confirms a swap and token balances. No mainnet broadcast.
