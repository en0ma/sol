# Non-negotiable project goal: Solana arbitrage discovery and execution

**Mission:** continuously discover, quote, rank, and atomically simulate profitable arbitrage across a broad and expanding universe of liquid Solana tokens, pools and DEX venues, including same-venue and cross-venue routes. Do not optimize a fixed losing route in place of opportunity discovery.

## Required pre-implementation checkpoint

Every feature or change must answer:
1. Does it expand **verified pool/venue coverage**, improve **amount-aware quoting**, improve **profitable route discovery**, enable **atomic swap execution**, or improve **freshness and continuous scanning**?
2. Which measurable metric changes (verified pools; supported quoting/execution adapters; tokens; scanning latency; viable quoted cycles; positive post-fee simulated PNL)?
3. Is the relevant venue actually executable? Program discovery or pool decoding alone does not qualify.
4. Does the code fail closed for unsupported layouts, unavailable accounts, stale slots, missing fees or residual intermediate tokens?
5. Is verification simulation-only through Surfpool with no mainnet swap broadcasting?

If a task improves none of these, postpone it. Always prioritize finding economically viable routes over repeated tuning of known losing swaps.

## Near-term development order

1. Widen live and bounded verified pool discovery; persist validated candidate registries, cover WSOL, major stablecoins and liquid tokens.
2. Implement missing pool layouts, **amount-aware direction-specific quotes** and swap builders for Raydium AMM v4, PumpSwap, Meteora DLMM/DAMM v2, and additional executable venues.
3. Rank 2–4 hop cycles using actual liquidity, integer token units, venue and transaction fees, slippage and optimal trade sizes.
4. Feed top-ranked *positive estimated net* candidates to signed atomic Surfpool simulations, verify every program invocation and end balances.
5. Refresh state and rescan continuously with bounded RPC budgets and freshness limits.
6. Never claim confirmed arbitrage or profitability based only on pool discovery, spot prices or a successful CI job.

## Coverage gates

Track pools in distinct stages: *recognized program* -> *decoded pool* -> *validated pool/vaults* -> *quoted exact input/output* -> *swap-built* -> *atomic simulation verified*. Only the last three can support actionable arbitrage claims; program identification does not imply support. Target 10–12 liquidity protocol families, initially 500–2,000 verified pools and 20–50 monitored liquid tokens; these are targets, not current coverage.

Mainnet swap broadcasts remain prohibited. Local ALT setup transactions to localhost Surfpool are a separate explicitly guarded operation.
