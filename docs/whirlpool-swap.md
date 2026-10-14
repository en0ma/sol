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
