# Six-venue 2–6-leg cyclic arbitrage: research-to-admission contract (2026-10-30)

This is a research and implementation plan, **not** live-execution authorization.

## Grounded external references
- Solana atomic transactions and failure rollback: https://solana.com/docs/core/transactions
- Solana legacy/v0/v1 transaction resource limits: https://solana.com/docs/core/transactions/versioned-transactions
- Solana compute fees and budgets: https://solana.com/docs/core/fees/compute-budget
- Solana CPI shared compute and privilege constraints: https://solana.com/docs/core/cpi
- OKX Pallas cyclic arbitrage graph, same-mint round trips, intermediate balance modes: https://github.com/okx/dex-solana-binary/blob/master/docs/cyclic-arbitrage.md
- Jupiter routePlan exact-in/exact-out representation: https://github.com/jup-ag/jupiter-quote-api-node/blob/main/swagger.yaml
- Concentrated liquidity per-tick exact-in math reference (concept only, not interchangeable with Solana venue math): https://github.com/Uniswap/v3-core/blob/main/contracts/libraries/SwapMath.sol
- Reference backtest graph/cost separation: https://github.com/lorenz-protocol/lorenz

## Correct pipeline / trust boundaries
1. Discover pool through venue-owned direct on-chain read (third-party index hints are not authority).
2. Authenticate pool program, pool/poolconfig/vault/mint identity, current slot and eligibility, fees, liquidity, account bytes.
3. Verify exact native integer quote against pinned official SDK AND genuinely signed isolated Surfpool output for both directions and two sizes. Preserve independent poststate and instruction-intent audit. Reject unsupported fee/mode/account variants.
4. Admit only independently accepted provenance to the **existing** shared registry. Historical source/SDK/signed hashes are immutable evidence, NOT current executable pricing.
5. Coordinator MUST newly reauthenticate each selected pool, quote all legs from coherent current state, inspect exact full-route accounts/compute/packet limits, sign/simulate only in isolated offline Surfpool, and independently reconcile SPL CPI per leg, terminal balance and rollback. Do not confuse candidate cycles with opportunities.

## Route model
A valid 2–6-leg cyclic route is tokens T0→T1→…→Tn, 2≤n≤6, Tn=T0. Each edge is a specific directed (venue, pool, input mint, output mint), with current authenticated state and exact integer quote function f_i(x). Propagate exact raw token units: x_(i+1)=f_i(x_i); never multiply floating indicative spot prices to assert a trade. Distinguish edge reuse and mutable shared pool state: if a pool is used twice, later quote must reflect earlier reserve/tick changes. Token identity requires full mint keys, not symbols.

Gross roundtrip Δgross = x_n−x_0 (start mint base units). Net economic opportunity additionally subtracts transaction base/priority fees, any required tip, setup/rent/borrow expense, and possible conversion of SOL-denominated costs into the start mint, with defensible live estimates. Optimize input size over bounded liquidity/fee/tick regimes rather than assume a positive tiny-size spread stays positive at scale. A quote-positive cycle is not net profitable until **all** costs and signed execution evidence are established.

## Execution
Solana instructions in a transaction succeed or all state changes revert (fees may still be charged). CPI shares compute budget. Legacy/v0 packets are limited to 1232 bytes and (current traditional mode) 1.4M CU; v0 uses address lookup tables. v1 increases transaction size to 4096 bytes but does not use ALTs; it requires separate compatibility testing and cannot be treated as implemented by this repo. Existing offline v0 ephemeral ALT is NOT a mainnet-ready ALT. Multi-transaction bundles are a separate mechanism and out of present scope. All signed simulation must occur on a new offline localhost fork, never on the source-connected process. Do not add live sendTransaction.

## Existing versus missing
Existing: arb/onchain_pool_discovery.py, arb/pool_registry.py, arb/six_venue_pipeline.py, arb/atomic_graph_coordinator.py, individual independent venue SDK/native/signature audits, isolated source/offline workflows.
Initial new boundary: arb/six_venue_registry_eligibility.py screens newer-format signed provenance and intentionally returns ZERO coordinator-eligible entries without fresh current state+quote and independent receipt re-attestation. Older Orca/DAMM v2/CPMM historical proofs need a separate evidence bridge, not automatic rejection of their history or automatic admission.
Missing: verified receipt-backed bridge for all six, live-state coherence and fee eligibility per candidate, usable-registry admission and coordinator consumption, 2–6-leg mutable-state accurate quote and net economics, end-to-end acceptance tests. Existing three-leg source fixture runner must not be presented as complete 2–6-leg admission.

## Next checkpoints (fail closed)
A. Prove provenance screening test passes, inspect CI.
B. Design explicit legacy receipt mapping and independent verification; never fabricate hashes.
C. Implement shared registry admission/readiness interface with independent per-venue auditors and fresh source revalidation, preserving existing registry and coordinator.
D. Expand multi-leg route planning and testing from existing 2–6-leg coordinator primitives; accurately track state shared between legs.
E. Offline-simulate signed candidate sequences and negative rollback controls; include 2,3,4,5,6 legs and compare raw SPL and compute evidence.
F. Reject any route whose net cost in common start-mint units is not credibly verified. No broadcasting.
