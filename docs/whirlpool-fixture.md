# Whirlpool fixture verification milestone

Candidate: `7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm`, cited in the open-source `whirlpool-essentials` Python example as SOL/USDC tick-spacing-8 Whirlpool.

This is **a candidate, not a verified result**. GitHub Actions' mainnet-fork job must check:
- Account owner matches Orca Whirlpool program and correct 653-byte discriminator.
- Both SPL vaults exist, match the pool's mints, have shared authority and nonzero balances.
- Active liquidity is nonzero and mint decimals can be read.
- Pool readiness gate passes, and optional spot-state report is uploaded.

Do not treat spot prices as executable quotes. Swap instruction construction, tick-array traversal, and atomic multi-hop simulations remain future stages. DEX HTTP APIs are never contacted.
