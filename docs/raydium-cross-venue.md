# Raydium CPMM cross-venue verification

Second venue: official Raydium cp-swap program
`CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C`.

`arb.raydium_cpmm` decodes its 637-byte `PoolState` on-chain
Anchor account and verifies SPL Token vault mints, reserves, shared
vault authority, pool owner, and swap-enable flag.

For discovery **only by explicit request**:
`python3 -m arb.raydium_cpmm --discover`. This performs two
strict `getProgramAccounts` filtered scans by account size and
exact mint offsets, never a global unfiltered program scan. Upstream
RPC providers may rate-limit it.

The fork job reports pinned Raydium pools separately and permits
`NOT_CONFIGURED`; **a deployed Raydium program does not mean a
Raydium swap was executed**. Cross-venue simulation remains blocked
until a second verified, compatible pool is found and its swap
instruction built.

Source: https://github.com/raydium-io/raydium-cp-swap/blob/master/programs/cp-swap/src/states/pool.rs
