# Incremental registry ingestion

`python3 -m arb.pool_registry_ingest --discovery path/to/report.json --output next.json`
merges new pool *identities* into the persistent registry, deduplicates
pool addresses, and revalidates every entry with local Solana RPC.
Discovered entries are untrusted: only freshly validated owners, mints,
vault balances and slots can be included in the output snapshot.

The script does not overwrite the source registry and refuses to publish
an updated snapshot when any verification fails (including rate limits).
Its CI artifact is an *optional proposed registry* for review, never an
automatic trade or commit. Broad program scans remain independent of
targeted registry refreshes. Execution and profitable opportunity claims
require subsequent full atomic fork simulation.
