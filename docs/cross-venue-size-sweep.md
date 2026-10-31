# Atomic cross-venue size sweep

`python3 -m arb.cross_venue_sweep` simulates three **real** single-transaction
Orca → Raydium routes on Surfpool, varying intermediate exact-output USDC
amounts: 1,000, 10,000, 50,000 base units. Each trade independently
creates ephemeral local WSOL/USDC accounts, builds both program instructions,
and verifies zero residual USDC. The maximum test WSOL input is 1,000,000
lamports. `getFeeForMessage` is deducted.

Profit candidates must pass both on-chain instructions, inventory closure,
a fee estimate, and a strict minimum net gain of 10,000 lamports. Negative
results are normal and should not be mislabeled as opportunities.
No live execution is allowed. Simulations do **not** guarantee future fill.

The test must remain RPC-only; never introduce DEX HTTP quote APIs.
