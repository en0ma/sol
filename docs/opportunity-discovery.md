# Opportunity discovery beyond SOL/USDC

The execution harness verifies one SOL/USDC pool on Orca and Raydium, but
actual arbitrage search needs a **graph of pools** across different tokens
and venues. `arb.onchain_pool_discovery` uses only the fork's Solana RPC
`getProgramAccounts`, with account-size and both mint memcmp filters,
and verifies candidate pool/token vault state with account reads. This
is **not** a DEX HTTP API, and it never sends transactions.

Allowlisted token starting points: WSOL, USDC, USDT, JUP. Default pair
searches: WSOL/USDT, WSOL/JUP, USDC/USDT. Set
`--pairs WSOL/USDT,WSOL/JUP` for bounded discovery. The mainnet-fork
CI probes WSOL/USDT and emits a JSON artifact. RPC rate limiting or
excess candidate counts mark results PARTIAL; empty discovery is not
evidence that pools do not exist globally.

Matching mints across two venues is **only a routing candidate**, not
an executable quote. Next: add layouts and simulators for additional
venues, directional swap quotes, route graph traversal, rate limits,
liquidity screening, then verify top opportunities atomically on Surfpool.
