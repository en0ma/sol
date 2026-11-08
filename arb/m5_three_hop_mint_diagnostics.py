"""Auditable mint-level aggregation of offline Surfpool shard results.

This module does not infer profitability, authorize execution, or upgrade
capture-only evidence. Only the signed-and-rollback-verified route IDs in
the shard metrics count toward verified start-mint coverage.
"""
from collections import Counter, defaultdict
import json
from pathlib import Path

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}


def build_report(reports):
    if not isinstance(reports,list) or len(reports)!=10:
        raise ValueError("ten independent shard metric reports required")
    shards={r.get("shard") for r in reports if isinstance(r,dict)}
    if shards!=set(range(10)):
        raise ValueError("unique shards 0..9 required")
    selected=set()
    verified=set()
    by_mint=defaultdict(list)
    all_attempted=set()
    all_verified=set()
    for report in reports:
        attempted=report.get("route_ids")
        signed=report.get("verified_route_ids")
        if (not isinstance(attempted,list) or len(attempted)!=14 or
                not isinstance(signed,list) or
                len(set(attempted))!=len(attempted) or
                not set(signed)<=set(attempted)):
            raise ValueError("invalid signed route identity inventory")
        if all_attempted.intersection(attempted) or all_verified.intersection(signed):
            raise ValueError("duplicate cross-shard route")
        all_attempted.update(attempted)
        all_verified.update(signed)
        mint_starts=report.get("selected_start_mints")
        signed_starts=report.get("verified_start_mints")
        if not isinstance(mint_starts,list) or not isinstance(signed_starts,list):
            raise ValueError("missing source-selected/signed start-mint coverage")
        if not set(signed_starts)<=set(mint_starts):
            raise ValueError("verified mint absent from selected shard")
        selected.update(mint_starts)
        verified.update(signed_starts)
        failures=report.get("failures")
        if not isinstance(failures,list) or len(failures)!=len(attempted)-len(signed):
            raise ValueError("failed route evidence count mismatches shard")
        for failure in failures:
            if (not isinstance(failure,dict) or
                    failure.get("id") not in attempted or
                    failure["id"] in signed or
                    not isinstance(failure.get("start_mint"),str) or
                    failure["start_mint"] not in mint_starts):
                raise ValueError("missing source-bound failed route start mint")
            by_mint[failure["start_mint"]].append(failure)
    if len(all_attempted)!=140:
        raise ValueError("missing attempted signed route identities")
    pending=sorted(selected-verified)
    rows=[]
    for mint in pending:
        failures=by_mint[mint]
        if not failures:
            raise ValueError("unverified mint without failed route evidence")
        counts=Counter(
            f"{failure.get('venue') or 'UNATTRIBUTED'}:"
            f"{failure.get('error_code') if failure.get('error_code') is not None else 'UNKNOWN'}"
            for failure in failures)
        rows.append({
            "start_mint":mint,
            "failed_route_count":len(failures),
            "failure_reason_counts":dict(sorted(counts.items())),
            "failed_routes":[{
                "id":f["id"],
                "venue":f.get("venue"),
                "pool":f.get("pool"),
                "error_code":f.get("error_code"),
                "orca_liquidity_cliff":f.get("orca_liquidity_cliff"),
                "orca_liquidity_audit_error":f.get("orca_liquidity_audit_error"),
                "attempted_exact_input_base_units":f.get("attempted_exact_input_base_units",[]),
            } for f in sorted(failures,key=lambda f:f["id"])],
            "signed_and_rollback_verified":False,
        })
    return {
        "status":"OFFLINE_SIGNED_START_MINT_GAP_DIAGNOSTICS",
        "attempted_routes":len(all_attempted),
        "verified_routes":len(all_verified),
        "source_selected_start_mints":len(selected),
        "signed_verified_start_mints":len(verified),
        "source_captured_but_not_signed_verified_start_mints":len(pending),
        "unverified_start_mints":rows,
        **SAFE,
    }


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--metrics",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    root=Path(args.metrics)
    reports=[json.loads(path.read_text())
             for path in sorted(root.glob("*/three-hop-shard-metrics.json"))]
    result=build_report(reports)
    Path(args.output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({
        "mint_diagnostics_status":result["status"],
        "source_captured_but_unverified_starts":
            result["source_captured_but_not_signed_verified_start_mints"],
        "unverified_start_mint_failure_causes":{
            row["start_mint"]:row["failure_reason_counts"]
            for row in result["unverified_start_mints"]},
        **SAFE,
    }))


if __name__=="__main__":
    main()
