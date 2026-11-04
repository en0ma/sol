# Three-hop atomic simulation evidence

CI #228 confirmed that a single 1,090-byte versioned Solana transaction
successfully executes all three programs on a mainnet-backed Surfpool fork:

1. Raydium CPMM: WSOL to USDC exact-output.
2. Raydium CLMM: USDC to RAY.
3. Orca Whirlpool: RAY to WSOL (5,000 RAY base-unit fixed input).

The simulation used 96,482 compute units, started with 1,000,000 WSOL
lamports and ended with 993,762 lamports. Residual USDC was zero;
**residual RAY was 314 base units**. The gross WSOL change was
**-6,238 lamports**. Network fee was unavailable, so net PNL is unknown.
This is **not** a fully closed arbitrage route or evidence of profit.

The current fixed-amount third leg deliberately fails the cycle_closed
gate when RAY is left over. Do not equate 3 successful swap instructions
with closed-route execution: a dynamic amount solution or exact-output
combination that also clears the other intermediate balance remains
necessary. The single swap transaction was *simulated only*;
local lookup-table provisioning is sent solely to localhost Surfpool.
