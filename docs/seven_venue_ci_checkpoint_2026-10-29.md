# Seven-venue CI and signed-evidence checkpoint — 2026-10-29

Repository: `en0ma/sol`. Branch: `feat/surfpool-ci-validation`. PR #1.

## Meaning of the checkmarks

Historical accepted milestones are preserved. A CI unit-test pass is **not** a new signed
Surfpool execution, and a registered pool is **not automatically** a signed-accepted pool.
The older three venues have successful historical signed execution and atomic-rollback
proof but their registry rows do not carry the newer `signed_provenance` schema.
Do not replace historical ✅ with ❌ merely because the evidence format differs.

| Milestone | Orca | Meteora DAMM v2 | Raydium CPMM | PumpSwap | Meteora DLMM | Raydium CLMM | Meteora DBC |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Authenticated source | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Original program ELF; 0 pools |
| Required liquidity state | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Not accepted |
| Native integer quote + reference parity | ✅ historical | ✅ historical | ✅ historical | ✅ (7 pools) | ✅ (6 pools) | ✅ (7 pools, single-tick restricted) | Not accepted |
| Four genuine signed isolated Surfpool swap trials per accepted pool | ✅ historical | ✅ historical | ✅ historical | ✅ (28 total) | ✅ (24 total) | ✅ (28 total) | 0 |
| Independent signed/SPL evidence | ✅ historical | ✅ historical | ✅ historical | ✅ | ✅ | ✅ | No |
| Signed registry evidence | ✅ historical legacy format | ✅ historical legacy format | ✅ historical legacy format | 7 pools | 6 pools | 7 pools | 0 |
| Shared coordinator / adapter | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Must reuse existing |

## Exact current registry inventory

Read from `arb/pool_registry.json` on 2026-10-29 before this report:
- Orca: **44** registered identities; **0** with the *new* per-pool `signed_provenance` key.
- Meteora DAMM v2: **14** registered; **0** with newer-format per-pool provenance.
- Raydium CPMM: **9** registered; **0** with newer-format per-pool provenance.
- PumpSwap: **10** registered; **7** with four unique transaction hashes each (**28** hashes).
- Meteora DLMM: **6** registered, **6** with four hashes each (**24**).
- Raydium CLMM: **7** registered, **7** with four hashes each (**28**).
- DBC: **0** registered; **0** signed.

Total: **90** registered identities, **20** newer-format signed provenance identities,
**80** signed transaction hashes in the newer registry schema. The first three venues
are **not** zero signed executions; their individual *four-swap-per-pool historical
pool counts* are not derivable from this schema alone and must be extracted from
historical acceptance receipts without inventing values.

## Previously inspected actual GitHub Actions evidence

- [Full 42 ordered-pair atomic proof](https://github.com/en0ma/sol/actions/runs/40142851937):
  independently audited `ordered_pair_verified: 42`, including 20/20 core venue
  signed atomic pair acceptances. These are ordered **pair** counts, not
  four-swap-per-pool counts.
- [Focused AMM v4 signed safety](https://github.com/en0ma/sol/actions/runs/40141205642):
  success, signed receipt and independent acceptance artifacts.
- [PumpSwap seven pools](https://github.com/en0ma/sol/actions/runs/40813671557):
  reported 28 signed trials, artifact `12872260133`.
- [DLMM three-plus-three pools](https://github.com/en0ma/sol/actions/runs/40819813329),
  [second acceptance](https://github.com/en0ma/sol/actions/runs/40851953257):
  six accepted pools, 24 trials across runs.
- [CLMM initial signed pool](https://github.com/en0ma/sol/actions/runs/40862666749),
  [six additional pools](https://github.com/en0ma/sol/actions/runs/40866278277):
  seven accepted, 28 transactions, independently audited. Restricted to
  single-tick swaps with supported fee modes.
- [DBC original ELF authentication](https://github.com/en0ma/sol/actions/runs/40865460033):
  success, but zero original VirtualPools authenticated because the provider
  throttled `getProgramAccounts`. No signed DBC acceptance.

## Fresh CI checkpoint and limits

The new `.github/workflows/seven-venue-checkpoint.yml` is a read-only
seven-venue regression and registry inventory workflow. It runs source,
pricing, signed-receipt safety tests across six accepted venues and the DBC
source-identity regressions. It uploads a machine-readable pool inventory.
It **does not** run 4 fresh signed swaps for every registered pool, nor
claim a new 42-pair acceptance or solve DBC pool discovery.

**Fresh execution outcome at report creation: NOT YET OBSERVED.**
Review the latest run of [Seven Venue Acceptance Checkpoint](https://github.com/en0ma/sol/actions/workflows/seven-venue-checkpoint.yml)
for its actual conclusion before marking this fresh run green.
The workflow is activated by PR changes (this addition) and manual dispatch,
subject to GitHub permissions and the PR event. Existing
`AMM v4 Focused Atomic CI` is the established broader PR regression.

## Next gates

1. Inspect new CI results and fix actual failures, without lowering checks.
2. Extract original three venues' exact accepted pool/trial identities from signed
   CI artifacts; retain historical acceptance labels while distinguishing
   registry formats.
3. For DBC, obtain genuine VirtualPool identity hints, authenticate state
   (PoolConfig/vaults/Clock), develop independent native integer/official SDK
   parity, and only then execute four actual signed isolated swaps per pool.
4. Do not broadcast to mainnet, expose secrets, or promote unsigned evidence.

This document is deliberately an evidence snapshot, not a claim of a currently
green new full seven-venue signed test run.
