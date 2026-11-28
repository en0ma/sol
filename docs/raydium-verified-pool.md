# On-chain Raydium CPMM pool verification

The second venue, Raydium CPMM, now has a verified SOL/USDC pool:
`7JuwJuNU88gurFnyWeiyGKbFmExMWcmRZntn9imEzdny`.

Verification evidence: Surfpool fork GitHub Actions [run 146](https://github.com/en0ma/sol/actions/runs/38555321414) read at slot 456818333: program owner
`CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C`; SOL token0
mint; USDC token1 mint; swaps enabled; reserve balance checks for
both SPL vaults succeeded. Vault balances were 416748355 (WSOL base
units) and 44803022 (USDC base units) in that snapshot.

This is independent of any Raydium HTTP API. The pool fixture is
pinned so new CI runs revalidate it at their current fork state.
**No Raydium swap has been simulated or profit established yet.**
