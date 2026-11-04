# RPC backfill cadence and registry integration

Routine push and PR CI uses targeted getAccountInfo/getMultipleAccounts
refresh of the known-pool registry and atomic Surfpool simulations.
Rate-limited getProgramAccounts and historical getTransaction scans are
reserved for manually triggered workflow_dispatch backfills. This avoids
repeatedly exhausting the mainnet datasource quota on every commit.

During a manual backfill, **both** filtered account-discovery and history
reports are ingested through repeated --discovery arguments. Every entry is
rechecked against current on-chain pool and vault state before generating
the proposed-pool-registry artifact. The source registry is never mutated.

Neither workflow success nor an incomplete/empty backfill is evidence
of executable profit. The source/provider must support history and pool
account reads for discovery to populate additional real pools.
