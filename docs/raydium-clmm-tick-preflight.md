# CLMM tick array preflight

Raydium CLMM has 60 ticks per array and derives tick-array PDAs
from `tick_array`, pool key, and **big-endian signed i32 start tick**.
The packed account size is 10,240 bytes; the local preflight checks
owner, discriminator, pool address and exact start tick. It checks
bounded neighboring arrays in trade direction. Missing arrays are
reported as unavailable, not fabricated.

Reference: https://github.com/raydium-io/raydium-clmm/blob/master/programs/amm/src/states/tick_array.rs

This is not yet initialized-array bitmap traversal, nor an actual swap
simulation. A valid array alone cannot admit CLMM to execution routing.
