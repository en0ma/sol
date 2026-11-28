"""Fail-closed orchestration and evidence checks for the Blockzilla experiment."""
import argparse
from collections import Counter
import json
from pathlib import Path

from arb.blockzilla_discovery import SAFE, VENUES, address, digest, registry_ids
from arb.m5_start_mint_expansion import topology


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe(report):
    require(isinstance(report, dict) and report.get("schema") == 1
            and all(report.get(k) is False for k in SAFE), "invalid safe report")


def http_route(report, exit_code):
    """Return the only two admitted routing outputs, from the actual report."""
    safe(report)
    blocks = report.get("crosschecked_blocks")
    require(type(blocks) is int and blocks >= 0, "invalid crosschecked block count")
    if exit_code == 0 and report.get("status") == "HISTORICAL_HINTS_ONLY" and blocks > 0:
        return "true"
    if exit_code == 2 and report.get("status") == "NO_CROSSCHECKED_BLOCKS" and blocks == 0:
        require(report.get("candidate_hints") == [], "failed HTTP report contains hints")
        return "false"
    raise ValueError("HTTP exit code and evidence disagree")


def write_http_output(report_path, exit_code, output_path):
    route = http_route(json.loads(Path(report_path).read_text()), exit_code)
    # GitHub's step-output file, not stdout or a shell interpolation.
    with Path(output_path).open("a", encoding="utf-8") as stream:
        stream.write("usable=" + route + "\n")
    return route


def check_jobs(http, route, native, source):
    require(http == "success", "HTTP probe did not finish successfully")
    require(route in ("true", "false"), "missing or malformed HTTP routing output")
    if route == "true":
        require(native == "skipped", "unexpected native execution on HTTP path")
    else:
        require(native == "success", "native archive fallback did not succeed")
    require(source == "success", "source authentication did not succeed")


def identities(rows):
    require(isinstance(rows, list), "candidate list required")
    ids = set()
    for row in rows:
        require(isinstance(row, dict) and row.get("venue") in VENUES, "invalid candidate venue")
        key = (row["venue"], address(row["address"]))
        require(key not in ids, "duplicate candidate")
        ids.add(key)
    return ids


def check_evidence(directory, baseline, route):
    """Verify the actual artifact rather than relying on green job statuses."""
    root = Path(directory)
    hint_raw = (root / "historical-hints.json").read_bytes()
    hints = json.loads(hint_raw)
    source = json.loads((root / "source-authentication.json").read_text())
    safe(hints)
    safe(source)
    require(hints.get("status") == "HISTORICAL_HINTS_ONLY"
            and type(hints.get("crosschecked_blocks")) is int
            and hints["crosschecked_blocks"] > 0, "no independently checked blocks")
    if route == "true":
        checks = [b for b in hints.get("blocks", []) if b.get("crosschecked") is True]
        require(len({b["slot"] for b in checks}) == hints["crosschecked_blocks"]
                and all(b.get("sample", {}).get("block_identity_matched") is True
                        and b.get("sample", {}).get("transaction_matched") is True
                        for b in checks), "missing independent HTTP checks")
    elif route == "false":
        require(hints.get("archive_source_mode") == "PINNED_COMPACT_V2_PROGRAM_DUMP_PLUS_FINALIZED_RPC",
                "native source mode mismatch")
        require(hints.get("archive_packet_bytes_compared") is False,
                "native packet comparison cannot be claimed")
        matches = [x for x in hints.get("sample_checks", []) if x.get("matched") is True]
        require(len({x["slot"] for x in matches}) == hints["crosschecked_blocks"]
                and len({x["signature"] for x in matches}) == hints.get("crosschecked_transactions")
                and all(x.get("scope") == "SIGNATURE_SLOT_INDEX_STATUS_AND_PROGRAM"
                        for x in matches), "missing native membership checks")
    else:
        raise ValueError("invalid evidence route")
    require(source.get("status") == "SOURCE_AUTHENTICATION_EXPERIMENT"
            and source.get("hint_report_sha256") == digest(hint_raw),
            "source report does not bind the checked hints")
    require(all(source.get(k) is False for k in
                ("admitted_to_primary_registry", "signed_simulation_verified", "profit_verified")),
            "experimental report promoted beyond evidence")
    require(source.get("topology_is_hint_level") is True
            and source.get("baseline_pool_count") == len(baseline), "baseline scope mismatch")
    candidates = identities(hints.get("candidate_hints"))
    require(not candidates & registry_ids(baseline), "candidate already in baseline")
    pools = source.get("new_source_verified_pools")
    verified = identities(pools)
    require(verified <= candidates and source.get("new_source_verified_pool_count") == len(verified)
            and source.get("new_source_verified_by_venue") == dict(Counter(v for v, _ in verified)),
            "verified pool counts or identities mismatch")
    require(all(p.get("source_verified_only") is True
                and type(p.get("source_slot")) is int and p["source_slot"] >= 0 for p in pools),
            "missing current source context")
    attempts = source.get("candidate_attempts")
    require(isinstance(attempts, list), "missing source attempts")
    require(not any(a.get("status") == "SOURCE_BATCH_UNAVAILABLE" for a in attempts),
            "source authentication incomplete: unavailable account batch")
    require(identities(attempts) == candidates, "not every candidate has an attempt record")
    require(all(a.get("status") in ("SOURCE_VERIFIED", "VERIFIED_POOL_BUDGET_REACHED",
                "NOT_PROGRAM_OWNED_POOL", "POOL_DECODER_OR_VAULT_VERIFICATION_REJECTED")
                for a in attempts), "unknown source attempt result")
    require({(a["venue"], a["address"]) for a in attempts if a["status"] == "SOURCE_VERIFIED"}
            == verified, "source attempt and verified identities disagree")
    before, after = topology(baseline), topology(baseline + pools)
    new_starts = sorted(set(after["three_hop_start_mints"]) - set(before["three_hop_start_mints"]))
    require(source.get("baseline_topology_starts") == before["three_hop_start_mint_count"]
            and source.get("experimental_topology_starts") == after["three_hop_start_mint_count"]
            and source.get("additional_topology_start_mints") == new_starts,
            "topology totals do not reconcile")
    return {"status": "BLOCKZILLA_EVIDENCE_GATE_PASSED",
            "route": "HTTP" if route == "true" else "NATIVE_COMPACT_V2",
            "crosschecked_blocks": hints["crosschecked_blocks"], "candidate_hints": len(candidates),
            "source_verified_pools": len(verified), "additional_hint_topology_starts": len(new_starts),
            "benefit_demonstrated": False, "signed_simulation_verified": False, **SAFE}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="mode", required=True)
    route = sub.add_parser("route")
    route.add_argument("--report", required=True)
    route.add_argument("--exit-code", type=int, required=True)
    route.add_argument("--github-output", required=True)
    jobs = sub.add_parser("jobs")
    for name in ("http", "route", "native", "source"):
        jobs.add_argument("--" + name, required=True)
    evidence = sub.add_parser("evidence")
    evidence.add_argument("--directory", required=True)
    evidence.add_argument("--registry", default="arb/pool_registry.json")
    evidence.add_argument("--route", required=True)
    args = p.parse_args()
    if args.mode == "route":
        print("HTTP usable=" + write_http_output(args.report, args.exit_code, args.github_output))
    elif args.mode == "jobs":
        check_jobs(args.http, args.route, args.native, args.source)
    else:
        baseline = json.loads(Path(args.registry).read_text())["pools"]
        print(json.dumps(check_evidence(args.directory, baseline, args.route), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
