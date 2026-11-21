# Incremental pool discovery from on-chain transaction history

`python3 -m arb.onchain_history_discovery` enumerates a bounded number of
transaction signatures mentioning verified DEX program IDs, retrieves the
Solana JSON transactions, and probes the referenced account keys for
matching owner/layout. Candidate pool accounts are independently verified
using fresh token-vault reads. This uses *only* Solana RPC.

The history window is a sampling mechanism, **not** comprehensive pool
enumeration: program-signature RPC indexes may be sparse/rate-limited,
and signatures may be missing or irrelevant. Absence of pools is not proof
there are no opportunities. All errors mark reports PARTIAL; only verified
pools may be passed to the existing registry ingestion tool.
