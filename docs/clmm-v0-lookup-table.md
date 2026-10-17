# CLMM versioned-transaction compression

`arb.clmm_v0` loads an existing on-fork Address Lookup Table using
Solana JSON-RPC, rejects incorrectly owned/deactivated/malformed ALT
accounts, and compiles a signed v0 transaction. The compiler requires
the serialized packet to fit within **1,232 bytes**.

Set `SURFPOOL_CLMM_ALT_ADDRESS` only for an ALT **already present** on the
isolated fork. No ALT setup, mainnet broadcast, or lookup-table mutation
is performed by this code. If the ALT is missing, the simulation reports
`ALT_REQUIRED` instead of falsely claiming a working CLMM swap.
An ALT must hold enough non-signer accounts to reduce the 1,548-byte
legacy transaction below the packet limit. The larger route also
requires actual swap simulation and verified post-swap balances.
