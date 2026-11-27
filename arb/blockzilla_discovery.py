"""Bounded Blockzilla historical discovery, independent sample checks and source authentication.

Historical instruction accounts are untrusted hints. Existing pool decoders
and vault verifiers authenticate them; no registry admission or signing.
"""
import argparse
import base64
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen

from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from arb.onchain_pool_discovery import VENUES, verify
from arb.m5_start_mint_expansion import topology
from arb.pumpswap_local_simulation import local_rpc_only
from arb.rpc import call

SAFE = {"actionable": False, "broadcast": False, "live_execution_approved": False}
PROGRAMS = {info[0]: venue for venue, info in VENUES.items()}
BASE_URL = "https://getblock.blockzilla.dev/block/"
SAMPLE_SLOT = 250000000
MAX_BLOCK_BYTES = 24 * 1024 * 1024
MAX_TOTAL_BYTES = 96 * 1024 * 1024


def address(value):
    if not isinstance(value, str) or str(Pubkey.from_string(value)) != value:
        raise ValueError("invalid public key")
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


def registry_ids(rows):
    topology(rows)
    return {(row["venue"], row["address"]) for row in rows}


def fetch_block(slot, limit):
    if type(slot) is not int or slot < 0 or not 1 <= limit <= MAX_BLOCK_BYTES:
        raise ValueError("invalid archive fetch budget")
    req = Request(BASE_URL + str(slot) + ".json",
                  headers={"Accept": "application/json", "Accept-Encoding": "identity"})
    with urlopen(req, timeout=20) as response:
        return response.read(limit + 1)


def parse_block(raw):
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("error") is not None:
        raise ValueError("archive error")
    block = payload.get("result", payload)
    if not isinstance(block, dict) or not isinstance(block.get("transactions"), list):
        raise ValueError("archive block transactions unavailable")
    address(block.get("blockhash"))
    if type(block.get("parentSlot")) is not int or block["parentSlot"] < 0:
        raise ValueError("archive block parent unavailable")
    return block


def loaded(meta):
    value = meta.get("loadedAddresses")
    if value is None:
        return [], []
    if not isinstance(value, dict):
        raise ValueError("malformed loaded addresses")
    result = []
    for name in ("writable", "readonly"):
        keys = value.get(name)
        if not isinstance(keys, list):
            raise ValueError("missing loaded address class")
        result.append([address(a) for a in keys])
    return tuple(result)


def inner(meta):
    groups = meta.get("innerInstructions")
    if groups is None:
        return None
    if not isinstance(groups, list):
        raise ValueError("malformed CPI metadata")
    result = []
    for group in groups:
        index = group["index"]
        if type(index) is not int or not isinstance(group["instructions"], list):
            raise ValueError("malformed CPI group")
        children = []
        for ix in group["instructions"]:
            if (type(ix.get("programIdIndex")) is not int
                    or not isinstance(ix.get("accounts"), list)
                    or not all(type(a) is int for a in ix["accounts"])
                    or not isinstance(ix.get("data"), str)):
                raise ValueError("unresolved CPI")
            children.append((ix["programIdIndex"], tuple(ix["accounts"]), ix["data"]))
        result.append((index, children))
    return result


def decode_transaction(row):
    """Resolve legacy/v0 direct and CPI indexes; failed/unknown txs excluded."""
    meta = row.get("meta")
    if not isinstance(meta, dict) or "err" not in meta:
        raise ValueError("unknown transaction status")
    if meta["err"] is not None:
        return None
    encoded = row.get("transaction")
    if (not isinstance(encoded, list) or len(encoded) != 2 or encoded[1] != "base64"
            or not isinstance(encoded[0], str)):
        raise ValueError("unsupported transaction encoding")
    wire = base64.b64decode(encoded[0], validate=True)
    if not 1 <= len(wire) <= 1232:
        raise ValueError("invalid packet length")
    tx = VersionedTransaction.from_bytes(wire)
    if not tx.signatures:
        raise ValueError("missing signature")
    msg = tx.message
    static = [str(a) for a in msg.account_keys]
    lw, lr = loaded(meta)
    lookups = getattr(msg, "address_table_lookups", ())
    if (len(lw) != sum(len(x.writable_indexes) for x in lookups)
            or len(lr) != sum(len(x.readonly_indexes) for x in lookups)):
        raise ValueError("unresolved address lookup")
    keys = static + lw + lr
    header = msg.header
    required = header.num_required_signatures
    if not 1 <= required <= len(static):
        raise ValueError("invalid signer count")
    writable = (set(range(required - header.num_readonly_signed_accounts))
                | set(range(required, len(static) - header.num_readonly_unsigned_accounts))
                | set(range(len(static), len(static) + len(lw))))
    cpi = inner(meta)
    instructions = [(ix.program_id_index, tuple(ix.accounts)) for ix in msg.instructions]
    for index, children in cpi or []:
        if not 0 <= index < len(msg.instructions):
            raise ValueError("invalid CPI parent")
        instructions.extend((program, accounts) for program, accounts, _ in children)
    hints, venues = set(), set()
    for program, indexes in instructions:
        if not 0 <= program < len(keys) or any(not 0 <= a < len(keys) for a in indexes):
            raise ValueError("instruction index out of range")
        venue = PROGRAMS.get(keys[program])
        if venue:
            venues.add(venue)
            hints.update((venue, keys[a]) for a in indexes
                         if a in writable and a >= required and a != program)
    return {"signature": str(tx.signatures[0]), "wire_sha256": digest(wire),
            "transaction_base64": encoded[0], "hints": hints, "venues": venues,
            "loaded": (lw, lr), "inner": cpi}


def crosscheck(block, slot, sample, rpc):
    independent = rpc("getBlock", [slot, {"commitment": "finalized",
        "transactionDetails": "none", "rewards": False, "maxSupportedTransactionVersion": 0}])
    if (not isinstance(independent, dict)
            or independent.get("blockhash") != block["blockhash"]
            or independent.get("parentSlot") != block["parentSlot"]):
        raise ValueError("independent block identity mismatch")
    tx = rpc("getTransaction", [sample["signature"], {"encoding": "base64",
        "commitment": "finalized", "maxSupportedTransactionVersion": 0}])
    if not isinstance(tx, dict) or tx.get("slot") != slot:
        raise ValueError("independent transaction slot mismatch")
    decoded = decode_transaction(tx)
    if decoded is None or any(decoded[k] != sample[k] for k in
                              ("signature", "wire_sha256", "loaded", "inner")):
        raise ValueError("independent transaction payload mismatch")
    return {"signature": sample["signature"], "wire_sha256": sample["wire_sha256"],
            "transaction_base64": sample["transaction_base64"],
            "block_identity_matched": True, "transaction_matched": True,
            "scope": "ONE_TRANSACTION_SAMPLE_NOT_FULL_BLOCK_ATTESTATION"}


def scan(rpc_url, baseline, *, start_slot=0, blocks=6, keys_per_venue=24,
         fetcher=fetch_block, rpc_call=call):
    if (not rpc_url or type(start_slot) is not int or start_slot < 0
            or type(blocks) is not int or not 1 <= blocks <= 8
            or type(keys_per_venue) is not int or not 1 <= keys_per_venue <= 32):
        raise ValueError("invalid discovery scope")
    old = registry_ids(baseline)
    began = time.monotonic()
    rpc_counts, errors = Counter(), []

    def rpc(method, params):
        rpc_counts[method] += 1
        return rpc_call(rpc_url, method, params, timeout=20, retries=1)

    if start_slot:
        scopes = [(s, "EXPLICIT_RANGE") for s in range(start_slot, start_slot + blocks)]
    else:
        scopes = [(SAMPLE_SLOT, "DOCUMENTED_HISTORICAL_ANCHOR")]
        try:
            head = rpc("getSlot", [{"commitment": "finalized"}])
            if type(head) is not int or head <= 864000:
                raise ValueError("invalid finalized head")
            scopes.extend((s, "RECENT_MINUS_864000_SLOTS")
                          for s in range(head - 864000, head - 864000 + blocks))
        except Exception as exc:
            errors.append({"stage": "finalized_head", "error_class": type(exc).__name__})
    total_bytes, evidence = 0, []
    counts, first, venue_tx, multi_venue = Counter(), {}, Counter(), []
    for slot, scope in scopes:
        item = {"slot": slot, "scope": scope, "crosschecked": False}
        evidence.append(item)
        remaining = MAX_TOTAL_BYTES - total_bytes
        if remaining <= 0:
            item["status"] = "TOTAL_BYTE_BUDGET_EXHAUSTED"
            continue
        limit = min(MAX_BLOCK_BYTES, remaining)
        tick = time.monotonic()
        try:
            raw = fetcher(slot, limit)
            total_bytes += len(raw)
            item["bytes_read"] = len(raw)
            if len(raw) > limit:
                raise ValueError("block byte budget exceeded")
            item["archive_sha256"] = digest(raw)
            block = parse_block(raw)
            if block["parentSlot"] >= slot:
                raise ValueError("block parent not earlier than slot")
            item["blockhash"] = block["blockhash"]
            rows = []
            skipped = failed = 0
            for tx in block["transactions"]:
                try:
                    decoded = decode_transaction(tx)
                    if decoded is None:
                        failed += 1
                    else:
                        rows.append(decoded)
                except Exception:
                    skipped += 1
            item.update({"transaction_count": len(block["transactions"]),
                         "failed_transactions": failed, "unresolved_transactions": skipped,
                         "decoded_successful_transactions": len(rows)})
            if not rows:
                raise ValueError("no successful decodable sample")
            sample = next((x for x in rows if x["venues"]), rows[0])
            item["sample"] = crosscheck(block, slot, sample, rpc)
            item["crosschecked"] = True
            item["status"] = "BLOCK_SAMPLE_CROSSCHECKED"
            for row in rows:
                venue_tx.update(row["venues"])
                if len(row["venues"]) >= 2 and len(multi_venue) < 100:
                    multi_venue.append({"slot": slot, "signature": row["signature"],
                                        "venues": sorted(row["venues"]), "profit_verified": False})
                for hint in row["hints"] - old:
                    counts[hint] += 1
                    first.setdefault(hint, {"slot": slot, "signature": row["signature"]})
        except Exception as exc:
            # Transport exception strings can contain upstream credentials.
            item["status"] = "ARCHIVE_OR_INDEPENDENT_CHECK_FAILED"
            item["error_class"] = type(exc).__name__
            errors.append({"stage": "block", "slot": slot, "error_class": type(exc).__name__})
        finally:
            item["elapsed_seconds"] = round(time.monotonic() - tick, 3)
    grouped = defaultdict(list)
    for (venue, key), count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        grouped[venue].append({"venue": venue, "address": key, "observations": count,
                               "first_observation": first[(venue, key)]})
    selected = [row for venue in VENUES for row in grouped[venue][:keys_per_venue]]
    checked = sum(row["crosschecked"] for row in evidence)
    return {"schema": 1, "status": "HISTORICAL_HINTS_ONLY" if checked else "NO_CROSSCHECKED_BLOCKS",
            "archive_base_url": BASE_URL, "blocks": evidence, "crosschecked_blocks": checked,
            "archive_bytes_read": total_bytes, "elapsed_seconds": round(time.monotonic() - began, 3),
            "independent_rpc_logical_requests": dict(rpc_counts), "errors": errors,
            "successful_dex_transactions_by_venue": dict(venue_tx),
            "distinct_novel_hints_by_venue": {v: len(grouped[v]) for v in VENUES},
            "candidate_hints": selected, "multi_venue_transaction_leads": multi_venue,
            "historical_candidates_are_untrusted": True, **SAFE}


def authenticate(rpc, baseline, report, *, max_verified_per_venue=4,
                 rpc_call=call, verify_pool=verify):
    local_rpc_only(rpc)
    if (report.get("schema") != 1 or report.get("status") != "HISTORICAL_HINTS_ONLY"
            or not report.get("crosschecked_blocks") or any(report.get(k) is not False for k in SAFE)
            or type(max_verified_per_venue) is not int or not 1 <= max_verified_per_venue <= 8):
        raise ValueError("crosschecked bounded hint report required")
    old = registry_ids(baseline)
    hints = report.get("candidate_hints")
    if not isinstance(hints, list) or len(hints) > 32 * len(VENUES):
        raise ValueError("invalid candidate budget")
    grouped, seen = defaultdict(list), set()
    for hint in hints:
        venue, key = hint["venue"], address(hint["address"])
        if venue not in VENUES or (venue, key) in seen or (venue, key) in old:
            raise ValueError("invalid or duplicate novel candidate")
        seen.add((venue, key))
        grouped[venue].append(hint)
        if len(grouped[venue]) > 32:
            raise ValueError("per-venue candidate budget exceeded")
    verified, attempts, batch_requests = [], [], 0
    for venue in VENUES:
        group = grouped[venue]
        if not group:
            continue
        program, size, _, _, decoder = VENUES[venue]
        try:
            batch_requests += 1
            response = rpc_call(rpc, "getMultipleAccounts", [[h["address"] for h in group],
                                {"encoding": "base64", "commitment": "confirmed"}])
            values, slot = response.get("value"), response.get("context", {}).get("slot")
            if not isinstance(values, list) or len(values) != len(group) or type(slot) is not int:
                raise ValueError("source batch context incomplete")
        except Exception as exc:
            attempts.append({"venue": venue, "status": "SOURCE_BATCH_UNAVAILABLE",
                             "candidate_count": len(group), "error_class": type(exc).__name__})
            continue
        accepted = 0
        for hint, account in zip(group, values):
            key = hint["address"]
            item = {"venue": venue, "address": key, "initial_source_slot": slot}
            attempts.append(item)
            if accepted >= max_verified_per_venue:
                item["status"] = "VERIFIED_POOL_BUDGET_REACHED"
                continue
            if not account or account.get("owner") != program or account.get("executable") is not False:
                item["status"] = "NOT_PROGRAM_OWNED_POOL"
                continue
            try:
                raw = base64.b64decode(account["data"][0], validate=True)
                if size is not None and len(raw) != size:
                    raise ValueError("pool account size mismatch")
                result = verify_pool(rpc, venue, key, decoder(raw))
                mints = result["mints"]
                if (result.get("venue") != venue or result.get("address") != key
                        or not isinstance(mints, list) or len(mints) != 2
                        or address(mints[0]) == address(mints[1])
                        or type(result.get("slot")) is not int):
                    raise ValueError("source verifier identity/context mismatch")
                verified.append({"venue": venue, "address": key, "mints": mints,
                                 "source_slot": result["slot"], "source_verified_only": True,
                                 "historical_observation": hint["first_observation"]})
                accepted += 1
                item["status"] = "SOURCE_VERIFIED"
            except Exception as exc:
                item["status"] = "POOL_DECODER_OR_VAULT_VERIFICATION_REJECTED"
                item["error_class"] = type(exc).__name__
    before, after = topology(baseline), topology(baseline + verified)
    new_starts = sorted(set(after["three_hop_start_mints"]) - set(before["three_hop_start_mints"]))
    return {"schema": 1, "status": "SOURCE_AUTHENTICATION_EXPERIMENT",
            "baseline_scope": "COMMITTED_REGISTRY_HINTS_NOT_FRESHLY_REAUTHENTICATED_CONTROL",
            "baseline_pool_count": len(baseline), "new_source_verified_pools": verified,
            "new_source_verified_pool_count": len(verified),
            "new_source_verified_by_venue": dict(Counter(p["venue"] for p in verified)),
            "candidate_attempts": attempts, "source_batch_logical_requests": batch_requests,
            "baseline_topology_starts": before["three_hop_start_mint_count"],
            "experimental_topology_starts": after["three_hop_start_mint_count"],
            "additional_topology_start_mints": new_starts, "topology_is_hint_level": True,
            "admitted_to_primary_registry": False, "signed_simulation_verified": False,
            "profit_verified": False, **SAFE}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    read = sub.add_parser("scan")
    read.add_argument("--start-slot", type=int, default=0)
    read.add_argument("--blocks", type=int, default=6)
    read.add_argument("--keys-per-venue", type=int, default=24)
    source = sub.add_parser("authenticate")
    source.add_argument("--hints", required=True)
    for cmd in (read, source):
        cmd.add_argument("--registry", default="arb/pool_registry.json")
        cmd.add_argument("--output", required=True)
    args = parser.parse_args()
    baseline = json.loads(Path(args.registry).read_text())["pools"]
    if args.mode == "scan":
        result = scan(os.environ.get("BLOCKZILLA_INDEPENDENT_RPC_URL"), baseline,
                      start_slot=args.start_slot, blocks=args.blocks, keys_per_venue=args.keys_per_venue)
        write(args.output, result)
        print(json.dumps({k: result[k] for k in ("status", "crosschecked_blocks",
             "archive_bytes_read", "independent_rpc_logical_requests", "successful_dex_transactions_by_venue")}))
        return 0 if result["crosschecked_blocks"] else 2
    raw = Path(args.hints).read_bytes()
    result = authenticate("http://127.0.0.1:8899", baseline, json.loads(raw))
    result["hint_report_sha256"] = digest(raw)
    write(args.output, result)
    print(json.dumps({k: result[k] for k in ("status", "new_source_verified_pool_count",
         "baseline_topology_starts", "experimental_topology_starts", "additional_topology_start_mints")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
