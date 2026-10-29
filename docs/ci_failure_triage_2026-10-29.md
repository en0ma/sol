# CI failure triage — 2026-10-29

This note records **observed failures**, fixes and verification limits. A pushed
fix does not imply that the rerun is green.

## Observed failures

1. [DBC signed offline research #40911271286](https://github.com/en0ma/sol/actions/runs/40911271286)
   failed in *Independently reconcile original zero-fee curve mathematics*.
   The log's exact exception was
   `TypeError: walk() got an unexpected keyword argument 'input_amount'`.
   The new native multi-point walk requires `amount_in`, but the
   independent curve auditor still called `input_amount`.
   **Fixed:** `arb/meteora_dbc_native_curve_audit.py` now calls
   `walk(..., amount_in=actual)`. The separate full-fee parity caller
   already used `amount_in=excluded`. The source and official SDK
   quote stages had succeeded before this TypeError.

2. [CLMM six additional signed #40911271319](https://github.com/en0ma/sol/actions/runs/40911271319)
   failed in *Require genuine distinct signed 4 x 6 CLMM SDK/native/SPL
   results*, before registry admission. The exact error was
   `ValueError: CLMM official SDK tick path not in authenticated snapshot`.
   Live source discovery and SDK screening selected a pool with a SDK
   remaining tick-array path not present in its original authenticated
   tick snapshot. Signing rejected it correctly.
   **Fixed at selection boundary:** `tools/raydium_clmm_six_official_sdk_screen.js`
   now independently checks **every** SDK trial's remaining tick-array
   path for 1–5 unique addresses, all in `row.tick_capture.tick_arrays`
   with `present===true`. Any inconsistent candidate is rejected
   **before** six-pool signed execution, instead of failing after
   source/SDK selection. If fewer than six supported pools remain,
   the screening step still fails: this is intentional, not a false
   CI success.

3. [DBC six-source research #40908544803](https://github.com/en0ma/sol/actions/runs/40908544803)
   failed its real-source qualification for six distinct pools:
   **three of six** passed. Some others were migrated / unsupported.
   This is an actual live liquidity/source-availability shortfall,
   not a unit-test failure. Partial independently authenticated
   source artifacts are now retained before strict failure.

## Scope and next evidence gate

On the affected commit, independent source regression and the seven-venue
checkpoint had succeeded; failures were isolated to the named dynamic
research/signed acceptance jobs. Neither historical accepted venues
nor current signed registry entries should be downgraded based on a
failed attempted discovery of *new* live pools.

The next new Actions runs must establish green **on their own SHA**.
Source authenticity and quotes do not establish a signed DBC pool:
DBC acceptance remains 0/6 until real signed Ed25519/SPL audits and
existing registry signed provenance pass.

No mainnet writes are authorized.
