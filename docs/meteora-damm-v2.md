# Meteora DAMM v2 pool discovery

The 1112-byte bytemuck `Pool` layout from Meteora's official
`damm-v2-sdk/src/idl/cp_amm.json` supports account-level mint-pair
discovery. Token A/B mint offsets: **168/200**; vaults: **232/264**.
The decoder also checks the Pool discriminator, sqrt price, liquidity,
pool status, SPL classic vault mint identities and nonempty balances.

Source: https://github.com/MeteoraAg/damm-v2-sdk/blob/main/src/idl/cp_amm.json

This only enables pool-level discovery. Meteora DAMM v2 swap instruction
construction and execution remain NOT VERIFIED, and no arbitrage
opportunity is claimed. Rate-limited getProgramAccounts searches report
PARTIAL if the provider cannot fulfill them.
