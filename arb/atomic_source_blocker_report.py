"""Explain source discovery vs pool authentication vs route intersection failures.

Consumes read-only reports only; never queries RPC or claims execution.
"""
import argparse
import collections
import json
from pathlib import Path

def diagnose(probes,summaries):
    rows=[]
    totals=collections.Counter()
    venue_failure=collections.defaultdict(list)
    missing_venue=collections.Counter()
    for probe,summary in zip(probes,summaries):
        pools=probe.get("authenticated_pools",{})
        failures=probe.get("failed_pool_checks",[])
        for entry in failures:
            venue_failure[entry["venue"]].append({
                "pool":entry.get("pool"),"error_class":entry.get("error_class"),
                "diagnostic":entry.get("diagnostic")})
        by_route={(e["first_venue"],e["second_venue"]):e
                  for e in probe.get("route_candidates",[])}
        for exported in summary.get("routes",[]):
            first,second=exported["first_venue"],exported["second_venue"]
            key=(first,second)
            route=by_route.get(key,{})
            left=pools.get(first,[])
            right=pools.get(second,[])
            candidate_count=route.get("candidate_count",0)
            if exported["status"]=="AUTHENTICATED_DUAL_PROGRAM_SOURCE_FIXTURE":
                reason="FIXTURE_EXPORTED"
            elif not left or not right:
                reason="NO_AUTHENTICATED_POOL_FOR_VENUE"
                for v,items in ((first,left),(second,right)):
                    if not items:missing_venue[v]+=1
            elif not candidate_count:
                reason="NO_SHARED_AUTHENTICATED_MINT_PAIR"
            else:
                reason="ACCOUNT_OR_PROGRAM_EXPORT_FAILED"
            rows.append({"route":first+"__"+second,"first_venue":first,
                         "second_venue":second,"stage":reason,
                         "first_authenticated_pool_count":len(left),
                         "second_authenticated_pool_count":len(right),
                         "source_candidate_count":candidate_count,
                         "export_diagnostic":exported.get("reason"),
                         "signed_atomic_execution_verified":False})
            totals[reason]+=1
    if len(rows)!=44:
        raise ValueError("source probe/fixture reports must cover 10+10+24 route attempts")
    return {"status":"SOURCE_STAGE_BLOCKER_DIAGNOSTICS",
            "source_attempts":len(rows),"unique_ordered_pairs":len(set(x["route"] for x in rows)),
            "counts_by_stage":dict(totals),
            "venue_missing_authenticated_pool_impact":dict(missing_venue),
            "venue_pool_check_failures":dict(venue_failure),
            "routes":rows,"rpc_calls_performed":0,"broadcast":False,
            "signed_atomic_execution_verified":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--probes",nargs=3,required=True)
    p.add_argument("--summaries",nargs=3,required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    report=diagnose([json.loads(Path(p).read_text()) for p in args.probes],
                    [json.loads(Path(p).read_text()) for p in args.summaries])
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"counts_by_stage":report["counts_by_stage"],
                      "venue_impact":report["venue_missing_authenticated_pool_impact"]}))

if __name__=="__main__":main()
