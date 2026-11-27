"""Same observed historical slot-window control for Blockzilla discovery.

Direct finalized RPC block reads are a separate arm, not a substitute for
archive provenance. Both arms use the same venue sample quota, account-hint
quota, committed baseline and existing source pool/vault verifier.
"""
import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import time

from arb.blockzilla_discovery import (SAFE, VENUES, address, authenticate,
    decode_transaction, digest, registry_ids, write)
from arb.blockzilla_native_archive import read_manifest, read_venue_dump, select_samples
from arb.m5_start_mint_expansion import topology
from arb.rpc import call

SAMPLE_BUDGET = 2
HINT_BUDGET = 24
POOL_BUDGET = 4
MAX_SLOTS = 12
MAX_RESULT_JSON_BYTES = 96 * 1024 * 1024
MAX_BLOCK_RESULT_JSON_BYTES = 24 * 1024 * 1024


def archive_scope(directory):
    manifest, manifest_hash = read_manifest(directory)
    slots, counts, errors = set(), {}, []
    epoch = manifest["epoch"]
    for venue in VENUES:
        try:
            rows = read_venue_dump(directory, manifest, venue)
            venue_slots = {row["slot"] for row in rows}
            if any(s // 432000 != epoch for s in venue_slots):
                raise ValueError("archive row outside selected epoch")
            slots.update(venue_slots)
            counts[venue] = len(rows)
        except Exception as exc:
            errors.append({"venue": venue, "error_class": type(exc).__name__})
    if not slots or len(slots) > min(MAX_SLOTS, manifest["blocks_per_venue"]):
        raise ValueError("invalid observed archive slot scope")
    return {"slots": sorted(slots), "epoch": epoch, "manifest_sha256": manifest_hash,
            "archive_dump_counts": counts, "archive_scope_errors": errors,
            "requested_archive_rows": manifest["blocks_per_venue"],
            "all_requested_rows_have_successful_venue_records":
                len(slots) == manifest["blocks_per_venue"],
            "scope": "OBSERVED_SUCCESSFUL_ARCHIVE_VENUE_RECORD_SLOTS"}


def direct_control(rpc_url, baseline, slots, *, rpc_call=call):
    if (not rpc_url or not isinstance(slots, list) or not 1 <= len(slots) <= MAX_SLOTS
            or any(type(s) is not int or s < 0 for s in slots)
            or sorted(set(slots)) != slots):
        raise ValueError("invalid direct control slot scope")
    began = time.monotonic()
    old = registry_ids(baseline)
    rows, decoded, blocks, errors = defaultdict(list), {}, [], []
    rpc_counts, result_bytes = Counter(), Counter()
    for slot in slots:
        block_result = {"slot": slot, "completed": False}
        blocks.append(block_result)
        if sum(result_bytes.values()) >= MAX_RESULT_JSON_BYTES:
            block_result["reason"] = "RESULT_JSON_BUDGET_EXHAUSTED"
            continue
        try:
            rpc_counts["getBlock"] += 1
            result = rpc_call(rpc_url, "getBlock", [slot, {"commitment": "finalized",
                "encoding": "base64", "transactionDetails": "full", "rewards": False,
                "maxSupportedTransactionVersion": 0}], timeout=20, retries=1)
            size = len(json.dumps(result, separators=(",", ":")).encode())
            result_bytes["getBlock"] += size
            block_result["result_json_bytes"] = size
            if size > MAX_BLOCK_RESULT_JSON_BYTES or sum(result_bytes.values()) > MAX_RESULT_JSON_BYTES:
                raise ValueError("post-receive result JSON budget exceeded")
            if not isinstance(result, dict) or not isinstance(result.get("transactions"), list):
                raise ValueError("finalized block unavailable")
            address(result.get("blockhash"))
            if (type(result.get("parentSlot")) is not int or
                    not 0 <= result["parentSlot"] < slot):
                raise ValueError("invalid parent slot")
            unresolved, failed = 0, 0
            for index, tx in enumerate(result["transactions"]):
                try:
                    item = decode_transaction(tx)
                    if item is None:
                        failed += 1
                        continue
                except Exception:
                    unresolved += 1
                    continue
                if not item["venues"]:
                    continue
                key = (slot, item["signature"])
                if key in decoded:
                    raise ValueError("duplicate transaction identity in finalized block")
                decoded[key] = item
                for venue in item["venues"]:
                    rows[venue].append({"slot": slot, "tx_index": index,
                        "signature": item["signature"], "status": "Succeeded"})
            block_result.update({"completed": True, "blockhash": result["blockhash"],
                "transaction_count": len(result["transactions"]),
                "unresolved_transactions": unresolved, "failed_transactions": failed})
        except Exception as exc:
            block_result["error_class"] = type(exc).__name__
            errors.append({"slot": slot, "error_class": type(exc).__name__})
            # Never allow partially decoded block results into selection.
            for venue in VENUES:
                rows[venue] = [row for row in rows[venue] if row["slot"] != slot]
            decoded = {k: v for k, v in decoded.items() if k[0] != slot}
    samples, selected, counts, first, venue_tx = [], set(), Counter(), {}, Counter()
    for venue in VENUES:
        for row in select_samples(rows[venue], SAMPLE_BUDGET):
            key = (row["slot"], row["signature"])
            samples.append({"venue": venue, **row})
            if key in selected:
                continue
            selected.add(key)
            item = decoded[key]
            venue_tx.update(item["venues"])
            for hint in item["hints"] - old:
                counts[hint] += 1
                first.setdefault(hint, {"slot": key[0], "signature": key[1]})
    grouped = defaultdict(list)
    for (venue, key), count in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        grouped[venue].append({"venue": venue, "address": key, "observations": count,
                              "first_observation": first[(venue, key)]})
    checked = sum(b["completed"] for b in blocks)
    return {"schema": 1, "status": "HISTORICAL_HINTS_ONLY" if checked else "NO_CROSSCHECKED_BLOCKS",
        "archive_source_mode": "DIRECT_FINALIZED_RPC_CONTROL_NOT_ARCHIVE_EVIDENCE",
        "crosschecked_blocks": checked, "direct_rpc_blocks_completed": checked,
        "direct_rpc_slots_requested": slots, "blocks": blocks,
        "all_requested_blocks_completed": checked == len(slots),
        "successful_dex_transactions_by_venue": dict(venue_tx),
        "successful_dump_rows_by_venue": {v: len(rows[v]) for v in VENUES},
        "selected_samples": samples, "selected_distinct_transactions": len(selected),
        "independent_rpc_logical_requests": dict(rpc_counts),
        "successful_rpc_result_json_bytes": dict(result_bytes),
        "candidate_hints": [row for v in VENUES for row in grouped[v][:HINT_BUDGET]],
        "sample_budget_per_venue": SAMPLE_BUDGET, "errors": errors,
        "elapsed_seconds": round(time.monotonic() - began, 3), **SAFE}


def pairs(rows):
    by_pair = defaultdict(set)
    for row in rows:
        by_pair[tuple(sorted(row["mints"]))].add(row["venue"])
    return by_pair


def coverage(baseline, pools):
    before = topology(baseline)
    after = topology(baseline + pools)
    b_pairs, a_pairs = pairs(baseline), pairs(baseline + pools)
    before_shared = {p for p, venues in b_pairs.items() if len(venues) >= 2}
    after_shared = {p for p, venues in a_pairs.items() if len(venues) >= 2}
    novel = sorted(after_shared - before_shared)
    return {"new_source_verified_pools": len(pools),
        "new_source_verified_by_venue": dict(Counter(p["venue"] for p in pools)),
        "additional_distinct_mints": after["distinct_mints"] - before["distinct_mints"],
        "additional_three_hop_start_mints": sorted(set(after["three_hop_start_mints"])
                                                    - set(before["three_hop_start_mints"])),
        "additional_cross_venue_pairs": [{"mints": list(p), "venues": sorted(a_pairs[p])}
                                        for p in novel],
        "cross_venue_pair_count_before": len(before_shared),
        "cross_venue_pair_count_after": len(after_shared),
        "topology_is_hint_level": True}


def arm_metrics(hints, source, baseline):
    if (any(hints.get(k) is not False for k in SAFE)
            or any(source.get(k) is not False for k in SAFE)
            or any(source.get(k) is not False for k in ("admitted_to_primary_registry",
                "signed_simulation_verified", "profit_verified"))):
        raise ValueError("unsafe comparison evidence")
    pools = source["new_source_verified_pools"]
    attempted = source["candidate_attempts"]
    return {"candidate_hints": len(hints["candidate_hints"]),
        "source_batch_logical_requests": source["source_batch_logical_requests"],
        "source_attempt_statuses": dict(Counter(a["status"] for a in attempted)),
        "historical_logical_rpc_requests": hints["independent_rpc_logical_requests"],
        "successful_rpc_result_json_bytes": hints.get("successful_rpc_result_json_bytes"),
        "historical_read_elapsed_seconds": hints["elapsed_seconds"],
        "source_batch_unavailable": any(a["status"] == "SOURCE_BATCH_UNAVAILABLE" for a in attempted),
        **coverage(baseline, pools)}


def compare(scope, baseline, archive_hints, archive_source, control, control_source):
    if archive_hints.get("archive_manifest_sha256") != scope["manifest_sha256"]:
        raise ValueError("archive report manifest mismatch")
    if archive_hints.get("sample_budget_per_venue") != SAMPLE_BUDGET:
        raise ValueError("archive sample budget mismatch")
    if control["direct_rpc_slots_requested"] != scope["slots"]:
        raise ValueError("historical slot scope mismatch")
    a = arm_metrics(archive_hints, archive_source, baseline)
    c = arm_metrics(control, control_source, baseline) if control_source is not None else None
    archive_ids = registry_ids(archive_source["new_source_verified_pools"])
    control_ids = registry_ids(control_source["new_source_verified_pools"]) if control_source else set()
    a_samples = {(r["venue"], r["slot"], r["signature"]) for r in archive_hints["sample_checks"]}
    c_samples = {(r["venue"], r["slot"], r["signature"]) for r in control["selected_samples"]}
    matched_a = {r["signature"] for r in archive_hints["sample_checks"] if r.get("matched") is True}
    complete = (c is not None and control["all_requested_blocks_completed"]
                and not scope["archive_scope_errors"]
                and scope["all_requested_rows_have_successful_venue_records"]
                and not a["source_batch_unavailable"] and not c["source_batch_unavailable"])
    return {"schema": 1, "status": "COMPARISON_MEASURED" if complete else "COMPARISON_INCOMPLETE",
        "scope": scope, "same_sample_budget_per_venue": SAMPLE_BUDGET,
        "same_candidate_budget_per_venue": HINT_BUDGET, "same_verified_pool_budget_per_venue": POOL_BUDGET,
        "archive": a, "direct_rpc_control": c,
        "control_block_results": control["blocks"],
        "control_historical_rpc_requests": control["independent_rpc_logical_requests"],
        "control_successful_rpc_result_json_bytes": control["successful_rpc_result_json_bytes"],
        "sample_overlap_count": len(a_samples & c_samples),
        "archive_sample_count": len(a_samples), "control_sample_count": len(c_samples),
        "archive_independently_matched_unique_transactions": len(matched_a),
        "shared_verified_pool_identities": sorted([list(k) for k in archive_ids & control_ids]),
        "archive_only_verified_pool_identities": sorted([list(k) for k in archive_ids - control_ids]),
        "control_only_verified_pool_identities": sorted([list(k) for k in control_ids - archive_ids]),
        "measurement_limits": ["SAME_OBSERVED_SLOT_SCOPE_NOT_ALL_ARCHIVE_ROWS_IF_NO_VENUE_MATCH",
            "LOGICAL_RPC_CALLS_NOT_RETRIES_OR_BILLING",
            "RESERIALIZED_SUCCESSFUL_RPC_RESULTS_NOT_WIRE_BYTES",
            "RESULT_SIZE_LIMIT_IS_POST_RECEIVE_NOT_NETWORK_QUOTA",
            "SOURCE_BATCH_COUNTS_EXCLUDE_INTERNAL_VAULT_VERIFIER_RPC",
            "SOURCE_AUTHENTICATION_SEQUENTIAL_NOT_SHARED_SLOT_SNAPSHOT",
            "ARCHIVE_BUILD_CACHE_AND_NETWORK_COST_NOT_INCLUDED_IN_RPC_BYTES",
            "BASELINE_REGISTRY_HINTS_NOT_REAUTHENTICATED"],
        "benefit_demonstrated": False, "signed_simulation_verified": False, **SAFE}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive-directory", required=True)
    p.add_argument("--evidence-directory", required=True)
    p.add_argument("--registry", default="arb/pool_registry.json")
    args = p.parse_args()
    root = Path(args.evidence_directory)
    baseline = json.loads(Path(args.registry).read_text())["pools"]
    hint_raw = (root / "historical-hints.json").read_bytes()
    archive_hints = json.loads(hint_raw)
    archive_source = json.loads((root / "source-authentication.json").read_text())
    if archive_source["hint_report_sha256"] != digest(hint_raw):
        raise ValueError("archive source report hash mismatch")
    scope = archive_scope(args.archive_directory)
    control = direct_control(os.environ.get("BLOCKZILLA_INDEPENDENT_RPC_URL"), baseline, scope["slots"])
    write(root / "comparison-control-hints.json", control)
    control_source = None
    if control["direct_rpc_blocks_completed"]:
        control_source = authenticate("http://127.0.0.1:8899", baseline, control,
                                      max_verified_per_venue=POOL_BUDGET)
        control_source["hint_report_sha256"] = digest((root / "comparison-control-hints.json").read_bytes())
        write(root / "comparison-control-source.json", control_source)
    result = compare(scope, baseline, archive_hints, archive_source, control, control_source)
    write(root / "comparison.json", result)
    print(json.dumps(result, sort_keys=True))
    # An incomplete direct control is a measured limitation, not a failed
    # independent archive acceptance. Never claim comparative benefit.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
