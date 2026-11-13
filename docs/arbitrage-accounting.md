# Balance-aware arbitrage research

The forked atomic WSOL → USDC → WSOL simulation reports verified final
token-account balances. Any **residual USDC remains part of the portfolio**,
not an outright WSOL loss. `arb.whirlpool_accounting` computes a conservative
*indicative spot mark* in lamports using on-chain Whirlpool sqrtPriceX64,
the pool's trade fee, a configurable haircut (default 100 bps), and the
fork's `getFeeForMessage` estimate.

A marked portfolio P&L is **not an executable arbitrage quote**: liquidation
of residual USDC would require an additional transaction or swap, affect pool
state, cross tick arrays, pay fees, and possibly fail. Therefore
`execution_approved` is always false, regardless of the marked P&L.

The next proper gate is a 3-leg (or full second-leg sized) atomic route
that returns all intermediate inventory, and computes realized token delta
after network fees. Only that can substantiate execution profitability.
