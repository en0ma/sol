# Seventh venue: Meteora Dynamic Bonding Curve (DBC)

Chosen seventh venue: Meteora DBC `dynamic_bonding_curve`.
This is the distinct **launch-stage curve program** from Meteora DLMM
and DAMM v2, not a duplicate alias for either venue.

- Official program: `dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN`.
- Official pool authority: `FhVo3mqL8PW5pH5U2CN4XE33DokiyZnUwuGpH2hmHLuM`.
- Official reference: https://docs.meteora.ag/developer-guides/dbc
- Original program: https://github.com/MeteoraAg/dynamic-bonding-curve
- Reference SDK: `@meteora-ag/dynamic-bonding-curve-sdk`.

## Real starting evidence

`arb/meteora_dbc_seventh_venue_source.py` authenticates the
mainnet Solana upgradeable program owner, executable flag, ProgramData
address, loader tags, actual ELF signature and SHA-256. Its bounded
read-only VirtualPool scan requires an exact Anchor discriminator and
the DBC program as the direct account owner. It never signs or broadcasts
to mainnet and never admits a pool from a mere public API identity.

The first source workflow:
https://github.com/en0ma/sol/actions/runs/40865460033

Authenticated original on-chain ProgramData:
`HUfnSSiJxgspQm6C1rkqv6L3XgVtn7AESApgCQpCXCYh`.

Original executable ELF SHA-256:
`e2bfc853c1a1778dd8ee40ea9a0f3edf5587442360c57c685e7e3024ad0cad47`.

**Evidence boundary:** The current `SOLANA_MAINNET_RPC_URL` enforces
HTTP 429 on `getProgramAccounts` scans. The completed program ELF
authentication therefore records **zero authenticated VirtualPool
identities**, with
`scan_status=SCAN_THROTTLED_NO_POOL_AUTHENTICATION`.
A green program-authentication workflow must **not** be interpreted
as source-verified DBC pools or signed swap parity.

## Next acceptance gates

Read-only source identity discovery will need a permitted account index
or explicit on-chain pool identities, followed by synchronized
`VirtualPool` and `PoolConfig` state, base and quote token
vault accounts, the virtual reserve curve segment, clock-dependent
fees, Token-2022 transfer-hook compatibility where applicable, and
migration-state restrictions. Native exact integer buys and sells must
match the official SDK on original source bytes, then four distinct
genuine signed isolated Surfpool swaps **per DBC pool** need
independent SPL debit/credit and signed intent audits.

The existing shared registry and atomic coordinator remain the only
admission and scheduling paths. This seventh-venue start does not
create an independent coordinator, authorize mainnet trading, or
pretend any signed evidence exists.

## Follow-on implementation: bounded explicit on-chain identities

The source authenticator now accepts repeated `--pool-address` arguments
in place of the provider-throttled `getProgramAccounts` scan. These are
**untrusted identity hints**, not evidence until verified. The implementation
requires exactly `--count` distinct valid Solana pubkeys and reads them with
one confirmed `getMultipleAccounts` response and a recorded context slot.
Each account must be owned directly by the original DBC program, must not
be executable, and must carry the correct VirtualPool discriminator. Original
account bytes, lamports, SHA-256 and snapshot slot are retained. Any invalid
candidate fails closed; no partial registry admission occurs.

Example for one independently obtained candidate:

```bash
python3 -m arb.meteora_dbc_seventh_venue_source \
  --rpc "$SOLANA_MAINNET_RPC_URL" --count 1 \
  --pool-address "$UNTRUSTED_DBC_VIRTUAL_POOL" \
  --output dbc-seventh-explicit-source.json
```

No actual VirtualPool address is claimed in this section. This is source
infrastructure only; it does not verify configuration, pricing, SDK parity,
signed swaps or independent SPL changes. A green ELF-only workflow still
does not count as source pool acceptance.
