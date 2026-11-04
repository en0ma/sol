# Whirlpool swap construction

`arb.whirlpool_swap` creates the **legacy** Orca Whirlpool swap instruction
with Anchor's `global:swap` discriminator and the eleven required accounts,
using only local/on-chain inputs. This is not `swap_v2` and assumes the classic
SPL Token program. It does not submit transactions.

`encode_swap` is covered by offline tests. Full simulation requires properly
funded user token accounts, a validated oracle PDA, tick arrays in the correct
swap direction, and a current blockhash. To avoid false-positive claims,
the read-only inspection reports `swap_simulated: false` until a transaction
is actually simulated successfully. The existing transaction replay harness
can simulate signed transactions supplied as fixtures. No production signing
or broadcast path is enabled.

Reference: https://github.com/orca-so/whirlpools/blob/main/programs/whirlpool/src/instructions/swap.rs

## Orca oracle compatibility

The on-chain legacy `swap` instruction declares the oracle as an Anchor
`UncheckedAccount` with PDA seeds `[b"oracle", whirlpool]`.
The Orca program explicitly describes the account as unused for legacy
non-adaptive-fee pools; newer adaptive-fee pools require initialized Oracle
state. A missing account is **not** evidence that the Whirlpool is invalid.

The discriminator and program owner are validated if an Oracle account exists.
The pool's `fee_tier_index_seed` and `tick_spacing` determine whether this is
an adaptive-fee pool; see the official Orca source and SDK. For classic pools
with matching values, we allow a missing, correctly derived PDA.

This does not prove a successful swap. The preflight's randomly generated user
token accounts are deliberately unfunded; no live sending is possible.
