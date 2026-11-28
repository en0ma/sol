# Persistent on-chain pool registry

`arb/pool_registry.json` keeps known pool **identity hints** and is safe
to grow with externally supplied addresses only after independent validation.
`python3 -m arb.pool_registry` revalidates *every* entry using targeted
`getAccountInfo` and `getMultipleAccounts` reads. It rejects missing or
wrongly owned accounts, invalid decoders, mint drift, empty vaults, and
missing verification slots. It never trusts cached balances or old quotes.

The generated CI report provides a fresh slot-stamped verified graph of
pools sharing the same token mints. This deliberately avoids
`getProgramAccounts` for pinned pools. Broad discovery remains a separate,
rate-limited backfill stage. New identities should arrive from on-chain
events/account subscriptions or a controlled seed list, not DEX HTTP APIs.

A matching pair is **not** an executable arbitrage; live trading remains
disabled and every candidate still requires atomic fork verification.
