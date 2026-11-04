# Rate limits and expanded DEX program coverage

All Solana reads remain JSON-RPC against Surfpool. `arb.rpc.call` now retries
**only** HTTP 429/503 or RPC throttling errors, at most three retries
(default), using capped exponential full jitter. Invalid requests, broken
accounts and ordinary RPC errors fail immediately. Exhausted throttling
raises and discovery reports PARTIAL; no empty pool results are invented.

The fork already probes deployed Orca Whirlpool, Raydium CPMM, Raydium
CLMM, Meteora DLMM, and Meteora DAMM v2 program accounts. The new venue
capability registry exposes these five for monitoring but explicitly marks
Raydium CLMM, Meteora DLMM and DAMM v2 as **PROGRAM_ONLY** until each
account layout, mint/vault validation, and swap instruction are implemented.

This is *program support*, not a claim that their swaps execute. Pool scans
are still provider-rate-limited; a maintained event-fed pool registry or a
dedicated RPC endpoint is necessary for broad, reliable opportunity discovery.
No DEX HTTP quote or trading APIs are used.
