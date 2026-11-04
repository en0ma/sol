# RAY/WSOL third-leg candidate provenance

The earlier candidate `4c8jpn6sLMrZHMYNq6idFfMdLBWEqn1r1wFNtgsPqTwE` was determined on the mainnet-backed Surfpool fork to be owned by `DjVE6JNiYqPL2QXyCUUh8rNjHrbz9hXHNYt99MQ59qw1`, the legacy Orca Token Swap V1 program, **not** Orca Whirlpool. It cannot be decoded or swapped using the Whirlpool builder.

Two more publicly indexed RAY/SOL pool identities are deliberately treated as untrusted leads:
- `27ZbVdmoUhG639CfqG6kW8a4VXZeGBi8Dd4HUXjVDxeS` (https://www.geckoterminal.com/solana/pools/27ZbVdmoUhG639CfqG6kW8a4VXZeGBi8Dd4HUXjVDxeS)
- `5sgXhG1c9VBceg6aVQguK3NnbPfHinERZj86As6zW5Be` (https://www.geckoterminal.com/solana/pools/5sgXhG1c9VBceg6aVQguK3NnbPfHinERZj86As6zW5Be)

Read-only fork CI determines the actual owner, validates program-specific pool data, exact RAY/WSOL mint identities, vault balances and any required ticks. A listing's protocol name or prices are **never** used as execution evidence or off-chain quotes. No route is closed or profitable until all three legs execute atomically with zero residual intermediate balances and fee-adjusted PNL.
