# Meteora DLMM support

Meteora DLMM LbPair accounts are now decoded with the **904-byte**
bytemuck layout from the official Meteora DLMM SDK IDL. Token mints
are at offsets 88 and 120; reserves at 152 and 184. The discovery
layer uses narrowly filtered on-chain Solana RPC account queries,
validates the account discriminator, owner, bin step, SPL reserve mints
and balances, and excludes disabled or unsupported Token-2022 pools.

Official source: https://github.com/MeteoraAg/dlmm-sdk/blob/main/idls/dlmm.json

No Meteora swap instruction has been constructed or simulated. Correct
DLMM prices require active-bin/bin-array traversal and dynamic fee math:
vault balance ratios are not executable quotes. Even an admitted pool
must pass route-level transaction simulation to prove executable arbitrage.
