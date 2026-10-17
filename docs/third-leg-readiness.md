# Prospective third leg

A third leg RAY->WSOL is necessary to close the currently verified
WSOL->USDC->RAY route. An external listing provides an **untrusted**
RAY/SOL candidate (4c8jpn6sLMrZHMYNq6idFfMdLBWEqn1r1wFNtgsPqTwE).
The readiness probe uses only local Surfpool RPC to verify that the
account belongs to the Orca Whirlpool program, decodes RAY/WSOL mints,
verifies vault balances, and checks tick-array availability. Pool
discovery must never be confused with profitability or swap execution.

A verified third-leg pool is not sufficient: the route must fit a
Solana v0 transaction (possibly with a local ALT), execute all three
swaps in one simulation, finish with zero USDC/RAY, and report **net**
WSOL PNL including fees. Until then no closed-cycle opportunity is
claimed.
