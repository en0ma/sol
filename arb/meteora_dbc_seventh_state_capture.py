"""DBC same-response source reconciliation. No prices, signatures or RPC writes.

Only zero-copy VirtualPool with original SPL Token vaults is supported here.
The pool is reread alongside its referenced state to reject mutation between
identity lookup and the synchronized final source snapshot.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path

from solders.pubkey import Pubkey

from arb.rpc import call
from arb.meteora_dbc_seventh_venue_source import (
    DISC, PROGRAM, POOL_AUTHORITY, VIRTUAL_POOL_ACCOUNT_SIZE, SAFE,
)

TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_ACCOUNT_SIZE = 165


def key(raw):
    return str(Pubkey.from_bytes(raw))


def parse_pool(raw):
    if len(raw) != VIRTUAL_POOL_ACCOUNT_SIZE or raw[:8] != DISC:
        raise ValueError("DBC VirtualPool original size/discriminator invalid")
    # Upstream zero_copy PoolState starts after Anchor discriminator.
    # VolatilityTracker: 64 bytes, followed by five Pubkeys.
    o = 8 + 64
    names = ("config", "creator", "base_mint", "base_vault", "quote_vault")
    fields = {name: key(raw[o+i*32:o+(i+1)*32]) for i, name in enumerate(names)}
    o += len(names)*32
    fields["base_reserve"] = int.from_bytes(raw[o:o+8], "little")
    fields["quote_reserve"] = int.from_bytes(raw[o+8:o+16], "little")
    # Eight-byte quantities follow reserves: protocol/partner fee buckets.
    fields["sqrt_price_q64"] = int.from_bytes(raw[o+64:o+80], "little")
    # Migration flags follow 8-byte activation point.
    fields["pool_type"] = raw[o+88]
    fields["is_migrated"] = raw[o+89]
    fields["migration_progress"] = raw[o+92]
    if (fields["sqrt_price_q64"] == 0 or fields["pool_type"] != 0
            or fields["is_migrated"] != 0 or fields["migration_progress"] != 0):
        raise ValueError("DBC pool nontrading, migrated or unsupported token mode")
    return fields


def decode_account(account, *, owner, size=None):
    if (not isinstance(account, dict) or account.get("owner") != owner
            or account.get("executable") is not False
            or not isinstance(account.get("lamports"), int)
            or account["lamports"] < 0
            or not isinstance(account.get("data"), list)
            or len(account["data"]) != 2 or account["data"][1] != "base64"):
        raise ValueError("DBC contextual account owner/metadata invalid")
    raw = base64.b64decode(account["data"][0], validate=True)
    if size is not None and len(raw) != size:
        raise ValueError("DBC contextual account size invalid")
    return raw


def capture_pool(rpc, original):
    address = original["address"]
    first = base64.b64decode(original["account_base64"], validate=True)
    if hashlib.sha256(first).hexdigest() != original["account_sha256"]:
        raise ValueError("DBC identity source digest mismatch")
    fields = parse_pool(first)
    addresses = [address, fields["config"], fields["base_mint"],
                 fields["base_vault"], fields["quote_vault"]]
    if len(set(addresses)) != len(addresses):
        raise ValueError("DBC duplicated dependent account roles")
    response = call(rpc, "getMultipleAccounts", [addresses, {
        "encoding": "base64", "commitment": "confirmed",
        "minContextSlot": original["source_slot"]
    }])
    if (not isinstance(response, dict) or
            not isinstance(response.get("context"), dict) or
            type(response["context"].get("slot")) is not int or
            response["context"]["slot"] < original["source_slot"] or
            not isinstance(response.get("value"), list) or
            len(response["value"]) != len(addresses)):
        raise ValueError("DBC synchronized source context invalid")
    rows = response["value"]
    pool_raw = decode_account(rows[0], owner=PROGRAM, size=VIRTUAL_POOL_ACCOUNT_SIZE)
    if pool_raw != first:
        raise ValueError("DBC pool mutated between identity and dependency capture")
    cfg_raw = decode_account(rows[1], owner=PROGRAM)
    if len(cfg_raw) < 16:
        raise ValueError("DBC PoolConfig too short")
    mint_raw = decode_account(rows[2], owner=TOKEN_PROGRAM, size=82)
    vaults = []
    for n, row in enumerate(rows[3:]):
        raw = decode_account(row, owner=TOKEN_PROGRAM, size=TOKEN_ACCOUNT_SIZE)
        vaults.append(raw)
    # Source authentication of the mint and token accounts is necessary,
    # but the config's quote mint has not yet been decoded. Do not declare
    # this sufficient for trade acceptance.
    if key(vaults[0][:32]) != fields["base_mint"]:
        raise ValueError("DBC base vault mint mismatch")
    if any(key(v[32:64]) != POOL_AUTHORITY for v in vaults):
        raise ValueError("DBC token vault authority mismatch")
    if key(vaults[0][:32]) == key(vaults[1][:32]):
        raise ValueError("DBC both vaults use same mint")
    proof = {}
    for addr, raw, account in zip(addresses, [pool_raw, cfg_raw, mint_raw, *vaults], rows):
        proof[addr] = {
            "account_base64": account["data"][0], "lamports": account["lamports"],
            "sha256": hashlib.sha256(raw).hexdigest()
        }
    return {"status": "DBC_CONTEXTUAL_POOL_DEPENDENCIES_PARTIALLY_VERIFIED",
            "pool": address, "source_slot": response["context"]["slot"],
            "pool_fields": fields, "accounts": proof,
            "config_quote_mint_verified": False, "pricing_eligible": False,
            **SAFE}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rpc", required=True)
    p.add_argument("--identities", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    identities = json.loads(Path(args.identities).read_text())
    pools = identities.get("source_pools", [])
    if not pools:
        raise SystemExit("DBC no authenticated identity: refuse empty success")
    results = [capture_pool(args.rpc, p) for p in pools]
    Path(args.output).write_text(json.dumps({"pools": results}, indent=2)+"\n")
    print(json.dumps({"source_reconciled": len(results), "pricing_eligible": False}))


if __name__ == "__main__":
    main()
