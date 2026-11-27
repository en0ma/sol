"""Blockzilla public Compact V2 fallback, using the upstream program-dump CLI.

The uncredentialed reader runs in a separate CI job. Its signature leads are
not raw transaction proofs. Independent finalized RPC must confirm membership,
execution status and invoked program before deriving any account hints.
"""
import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import resource
import selectors
import shutil
import signal
import subprocess
import time

from solders.signature import Signature

from arb.blockzilla_discovery import (SAFE, VENUES, address, decode_transaction,
                                      digest, registry_ids, write)
from arb.rpc import call

UPSTREAM_REVISION = "c8265ad3e61a36e8f8f2dee49020f6bb0f01f220"
ARCHIVE_ROOT = "https://pub-97348740d6ef467aa2f1b4b62daa98dc.r2.dev/compact-v2/blockzilla-20261004"
DEFAULT_EPOCH = 1094
MAX_DUMP_BYTES = 4 * 1024 * 1024
MAX_CACHE_FILE_BYTES = 3 * 1024**3
MAX_CACHE_BYTES = 4 * 1024**3
MIN_FREE_BYTES = 512 * 1024**2
MAX_ROWS = 20000


def bounded_scope(epoch, first_block, blocks):
    if (type(epoch) is not int or not 0 <= epoch <= 4096
            or type(first_block) is not int or not 0 <= first_block < 432000
            or type(blocks) is not int or not 1 <= blocks <= 12
            or first_block + blocks > 432000):
        raise ValueError("invalid bounded archive scope")


def signature(value):
    if not isinstance(value, str) or str(Signature.from_string(value)) != value:
        raise ValueError("invalid transaction signature")
    return value


def parse_dump(raw):
    if len(raw) > MAX_DUMP_BYTES:
        raise ValueError("archive dump exceeds byte budget")
    if raw and not raw.endswith(b"\n"):
        raise ValueError("incomplete archive JSONL")
    lines = raw.splitlines()
    if len(lines) > MAX_ROWS:
        raise ValueError("archive dump exceeds row budget")
    rows, seen = [], set()
    for line in lines:
        row = json.loads(line)
        if (not isinstance(row, dict)
                or type(row.get("slot")) is not int or row["slot"] < 0
                or type(row.get("tx_index")) is not int or row["tx_index"] < 0
                or not isinstance(row.get("status"), str)):
            raise ValueError("malformed program dump row")
        # Failed and unknown status are not eligible. Missing signatures
        # on a successful row remain a visible invalid dump, not a lead.
        if row["status"] != "Succeeded":
            continue
        sig = signature(row.get("signature"))
        identity = (row["slot"], row["tx_index"], sig)
        if identity in seen:
            raise ValueError("duplicate archive transaction row")
        seen.add(identity)
        rows.append({"slot": row["slot"], "tx_index": row["tx_index"],
                     "signature": sig, "status": "Succeeded"})
    return rows


def limit_cache_file():
    # RLIMIT_FSIZE applies to *all* child file writes, including the archive
    # index and registry. Keep a separate, larger hard per-file cache limit.
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_CACHE_FILE_BYTES, MAX_CACHE_FILE_BYTES))


def cache_size(cache):
    """Logical on-disk file bytes, including unfinished temporary downloads."""
    total = 0
    for directory, dirs, files in os.walk(cache, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError("symlink in private archive cache")
        for name in files:
            path = Path(directory) / name
            try:
                total += path.stat().st_size
            except FileNotFoundError:
                # The reader can rename a control file while we inspect it.
                continue
    return total


def run_bounded_reader(command, raw_path, log_path, cache, env, *, timeout=150,
                       output_limit=MAX_DUMP_BYTES, cache_limit=MAX_CACHE_BYTES,
                       min_free=MIN_FREE_BYTES):
    """Bound output pipes separately from native archive control-file writes.

    Cache usage is sampled, not a hard aggregate network/disk quota; a separate
    per-file kernel limit and job deadline remain in force.
    """
    if (not 1 <= output_limit <= MAX_DUMP_BYTES or
            not 1 <= cache_limit <= MAX_CACHE_BYTES or timeout <= 0 or min_free < 0):
        raise ValueError("invalid reader budget")
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    begin = time.monotonic()
    peak = cache_size(cache)
    totals = {"stdout": 0, "stderr": 0}
    failure = None

    def budget():
        nonlocal peak
        peak = max(peak, cache_size(cache))
        if peak > cache_limit:
            return "CACHE_AGGREGATE_BUDGET_EXCEEDED"
        if shutil.disk_usage(cache).free < min_free:
            return "CACHE_DISK_FREE_FLOOR_REACHED"
        if time.monotonic() - begin >= timeout:
            return "READER_DEADLINE_EXCEEDED"
        return None

    def receipt(code, reason):
        return {"exit_code": code, "failure_reason": reason,
                "stdout_bytes_retained": totals["stdout"],
                "stderr_bytes_retained": totals["stderr"],
                "cache_peak_observed_bytes": peak,
                "cache_final_bytes": cache_size(cache)}

    with Path(raw_path).open("wb") as stdout, Path(log_path).open("wb") as stderr:
        failure = budget()
        if failure:
            return receipt(None, failure)
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=env, start_new_session=True, preexec_fn=limit_cache_file)
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ, ("stdout", stdout))
                selector.register(proc.stderr, selectors.EVENT_READ, ("stderr", stderr))
                while selector.get_map() or proc.poll() is None:
                    failure = budget()
                    if failure:
                        break
                    if not selector.get_map():
                        time.sleep(0.1)
                        continue
                    for event, _ in selector.select(timeout=0.2):
                        label, destination = event.data
                        chunk = os.read(event.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(event.fileobj)
                            continue
                        room = output_limit - totals[label]
                        retained = chunk[:room]
                        destination.write(retained)
                        totals[label] += len(retained)
                        if len(chunk) > room:
                            failure = label.upper() + "_BUDGET_EXCEEDED"
                            break
                    if failure:
                        break
                if not failure:
                    failure = budget()
        finally:
            # Terminate the whole reader process group on budget/exception,
            # including any descendants that might still hold output pipes.
            if failure or proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            proc.wait(timeout=10)
            proc.stdout.close()
            proc.stderr.close()
        if not failure and proc.returncode:
            if proc.returncode == -signal.SIGXFSZ:
                failure = "CACHE_PER_FILE_LIMIT_SIGNAL"
            else:
                failure = "READER_NONZERO_EXIT"
        return receipt(proc.returncode, failure)


def run_reader(binary, directory, *, epoch=DEFAULT_EPOCH, first_block=0, blocks=8):
    """No RPC credentials or signing; reuse a shared archive control-file cache."""
    bounded_scope(epoch, first_block, blocks)
    binary, root = Path(binary).resolve(strict=True), Path(directory).resolve()
    root.mkdir(parents=True, exist_ok=True)
    cache = root.parent / "native-archive-cache"
    url = f"{ARCHIVE_ROOT}/epoch-{epoch}"
    manifest = {"schema": 1, "upstream_revision": UPSTREAM_REVISION,
                "archive_url": url, "epoch": epoch, "first_block": first_block,
                "blocks_per_venue": blocks, "venues": {},
                "resource_limits": {"output_bytes_per_stream": MAX_DUMP_BYTES,
                    "cache_file_bytes": MAX_CACHE_FILE_BYTES,
                    "sampled_cache_bytes": MAX_CACHE_BYTES,
                    "min_free_disk_bytes": MIN_FREE_BYTES,
                    "deadline_seconds_per_venue": 150}, **SAFE}
    # Deliberately allow only basic runtime environment, not credentials.
    env = {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "SSL_CERT_FILE",
                                      "SSL_CERT_DIR") if k in os.environ}
    for venue, info in VENUES.items():
        raw_path, log_path = root / (venue + ".jsonl"), root / (venue + ".txt")
        command = [str(binary), "program-dump", "--epoch", str(epoch),
                   "--archive-url", url, "--cache-dir", str(cache),
                   "--first-block", str(first_block), "--max-blocks", str(blocks),
                   "--key", info[0], "--workers", "1", "--http-requests", "2",
                   "--http-range-mib", "2", "--stats"]
        started = time.monotonic()
        result = {"program_id": info[0], "completed": False}
        try:
            execution = run_bounded_reader(command, raw_path, log_path, cache, env)
            result.update(execution)
            if execution["exit_code"] == 0 and execution["failure_reason"] is None:
                raw = raw_path.read_bytes()
                rows = parse_dump(raw)
                result.update({"completed": True, "dump_sha256": digest(raw),
                               "dump_bytes": len(raw), "successful_rows": len(rows)})
        except Exception as exc:
            result["error_class"] = type(exc).__name__
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        manifest["venues"][venue] = result
        write(root / "manifest.json", manifest)
        print(json.dumps({"venue": venue, **result}), flush=True)
    return manifest


def read_manifest(directory):
    root = Path(directory)
    path = root / "manifest.json"
    if path.stat().st_size > MAX_DUMP_BYTES:
        raise ValueError("oversized archive manifest")
    raw = path.read_bytes()
    data = json.loads(raw)
    if (data.get("schema") != 1 or data.get("upstream_revision") != UPSTREAM_REVISION
            or any(data.get(k) is not False for k in SAFE)
            or not isinstance(data.get("venues"), dict)):
        raise ValueError("invalid archive manifest")
    epoch, first, blocks = data["epoch"], data["first_block"], data["blocks_per_venue"]
    bounded_scope(epoch, first, blocks)
    if data.get("archive_url") != f"{ARCHIVE_ROOT}/epoch-{epoch}":
        raise ValueError("unexpected archive identity")
    return data, digest(raw)


def sample_leads(directory, manifest, *, per_venue=2):
    if type(per_venue) is not int or not 1 <= per_venue <= 4:
        raise ValueError("invalid RPC sample budget")
    root = Path(directory)
    leads, rejected, counts = [], [], {}
    for venue, info in VENUES.items():
        result = manifest["venues"].get(venue, {})
        if result.get("completed") is not True or result.get("program_id") != info[0]:
            rejected.append({"venue": venue, "reason": "ARCHIVE_DUMP_NOT_COMPLETED"})
            continue
        try:
            path = root / (venue + ".jsonl")
            if path.stat().st_size > MAX_DUMP_BYTES:
                raise ValueError("oversized archive dump")
            raw = path.read_bytes()
            if digest(raw) != result.get("dump_sha256") or len(raw) != result.get("dump_bytes"):
                raise ValueError("archive dump digest mismatch")
            rows = parse_dump(raw)
            if len(rows) != result.get("successful_rows"):
                raise ValueError("archive dump count mismatch")
        except Exception as exc:
            rejected.append({"venue": venue, "reason": "ARCHIVE_DUMP_REJECTED",
                             "error_class": type(exc).__name__})
            continue
        counts[venue] = len(rows)
        # First spread samples across distinct slots, then fill from remaining rows.
        chosen, used_slots, used_signatures = [], set(), set()
        for distinct in (True, False):
            for row in rows:
                if row["signature"] in used_signatures or (distinct and row["slot"] in used_slots):
                    continue
                chosen.append(row)
                used_slots.add(row["slot"])
                used_signatures.add(row["signature"])
                if len(chosen) >= per_venue:
                    break
            if len(chosen) >= per_venue:
                break
        leads.extend({"venue": venue, **row} for row in chosen)
    return leads, rejected, counts


def verify_leads(rpc_url, baseline, directory, *, per_venue=2, rpc_call=call):
    """Cross-check archive signature/slot/index/status/program, not archive packet bytes."""
    if not rpc_url:
        raise ValueError("independent finalized RPC required")
    started = time.monotonic()
    old = registry_ids(baseline)
    manifest, manifest_hash = read_manifest(directory)
    leads, rejected, counts = sample_leads(directory, manifest, per_venue=per_venue)
    logical_rpc, observed, first = Counter(), Counter(), {}
    transactions, blocks, samples, venues = {}, {}, [], Counter()
    checked_signatures, checked_slots = set(), set()
    multi_venue, errors = [], list(rejected)

    def rpc(method, params):
        logical_rpc[method] += 1
        return rpc_call(rpc_url, method, params, timeout=20, retries=1)

    for lead in leads:
        sig, slot, venue, index = (lead[k] for k in ("signature", "slot", "venue", "tx_index"))
        sample = {**lead, "matched": False}
        samples.append(sample)
        stage = "FINALIZED_TRANSACTION"
        try:
            if sig not in transactions:
                tx = rpc("getTransaction", [sig, {"encoding": "base64",
                    "commitment": "finalized", "maxSupportedTransactionVersion": 0}])
                if not isinstance(tx, dict) or type(tx.get("slot")) is not int:
                    raise ValueError("transaction unavailable")
                decoded = decode_transaction(tx)
                if decoded is None or decoded["signature"] != sig:
                    raise ValueError("transaction identity/status mismatch")
                transactions[sig] = (tx["slot"], decoded)
            source_slot, decoded = transactions[sig]
            if source_slot != slot or venue not in decoded["venues"]:
                raise ValueError("archive slot or program mismatch")
            stage = "FINALIZED_BLOCK_MEMBERSHIP"
            if slot not in blocks:
                block = rpc("getBlock", [slot, {"commitment": "finalized",
                    "transactionDetails": "signatures", "rewards": False,
                    "maxSupportedTransactionVersion": 0}])
                if not isinstance(block, dict) or not isinstance(block.get("signatures"), list):
                    raise ValueError("finalized block membership unavailable")
                address(block.get("blockhash"))
                blocks[slot] = block
            block = blocks[slot]
            if index >= len(block["signatures"]) or block["signatures"][index] != sig:
                raise ValueError("archive transaction index mismatch")
            sample.update({"matched": True, "finalized_blockhash": block["blockhash"],
                           "rpc_wire_sha256": decoded["wire_sha256"],
                           "archive_packet_bytes_compared": False,
                           "scope": "SIGNATURE_SLOT_INDEX_STATUS_AND_PROGRAM"})
            checked_slots.add(slot)
            if sig not in checked_signatures:
                checked_signatures.add(sig)
                venues.update(decoded["venues"])
                if len(decoded["venues"]) >= 2:
                    multi_venue.append({"slot": slot, "signature": sig,
                        "venues": sorted(decoded["venues"]), "profit_verified": False})
                for hint in decoded["hints"] - old:
                    observed[hint] += 1
                    first.setdefault(hint, {"slot": slot, "signature": sig})
        except Exception as exc:
            sample.update({"failure_stage": stage, "error_class": type(exc).__name__})
            errors.append({"venue": venue, "signature": sig, "failure_stage": stage,
                           "error_class": type(exc).__name__})
    grouped = defaultdict(list)
    for (venue, key), count in sorted(observed.items(), key=lambda pair: (-pair[1], pair[0])):
        grouped[venue].append({"venue": venue, "address": key, "observations": count,
                               "first_observation": first[(venue, key)]})
    return {"schema": 1, "status": "HISTORICAL_HINTS_ONLY" if checked_slots else "NO_CROSSCHECKED_BLOCKS",
            "archive_source_mode": "PINNED_COMPACT_V2_PROGRAM_DUMP_PLUS_FINALIZED_RPC",
            "archive_manifest_sha256": manifest_hash, "upstream_revision": UPSTREAM_REVISION,
            "archive_url": manifest["archive_url"], "epoch": manifest["epoch"],
            "archive_successful_dump_rows_by_venue": counts,
            "crosschecked_blocks": len(checked_slots), "crosschecked_transactions": len(checked_signatures),
            "sample_checks": samples, "independent_rpc_logical_requests": dict(logical_rpc),
            "successful_dex_transactions_by_venue": dict(venues),
            "candidate_hints": [row for venue in VENUES for row in grouped[venue][:24]],
            "distinct_novel_hints_by_venue": {v: len(grouped[v]) for v in VENUES},
            "multi_venue_transaction_leads": multi_venue, "historical_candidates_are_untrusted": True,
            "archive_packet_bytes_compared": False, "errors": errors,
            "elapsed_seconds": round(time.monotonic() - started, 3), **SAFE}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    read = sub.add_parser("read")
    read.add_argument("--binary", required=True)
    read.add_argument("--directory", required=True)
    read.add_argument("--epoch", type=int, default=DEFAULT_EPOCH)
    read.add_argument("--first-block", type=int, default=0)
    read.add_argument("--blocks", type=int, default=8)
    check = sub.add_parser("check")
    check.add_argument("--directory", required=True)
    check.add_argument("--registry", default="arb/pool_registry.json")
    check.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.mode == "read":
        result = run_reader(args.binary, args.directory, epoch=args.epoch,
                            first_block=args.first_block, blocks=args.blocks)
        return 0 if any(v["completed"] and v.get("successful_rows", 0)
                        for v in result["venues"].values()) else 2
    baseline = json.loads(Path(args.registry).read_text())["pools"]
    result = verify_leads(os.environ.get("BLOCKZILLA_INDEPENDENT_RPC_URL"), baseline, args.directory)
    write(args.output, result)
    print(json.dumps({k: result[k] for k in ("status", "crosschecked_blocks",
        "crosschecked_transactions", "independent_rpc_logical_requests",
        "successful_dex_transactions_by_venue")}))
    return 0 if result["crosschecked_blocks"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
