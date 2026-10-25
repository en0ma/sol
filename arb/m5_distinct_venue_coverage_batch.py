"""Bounded multiple source-backed three-venue signed route trials.

Reuse the same authenticated three-pool exporter, signed coordinator, independent
CPI/rollback gate and quote diagnostic; no duplicate trading engine.
"""
import argparse,json
from pathlib import Path
from arb.next_ten_pair_fixture_export import export_three_venue
from arb.next_ten_signed_atomic_offline import run_three_venue
from arb.m5_three_distinct_venue_signed_acceptance import verify as accept
from arb.m5_three_venue_signed_quote_parity import compare
from arb.m5_three_venue_observed_economics import evaluate as evaluate_economics
from arb.next_ten_fork_pool_probe import authenticated_distinct_venue_triangles,select_distinct_triangle_coverage
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def source_batch(rpc,readiness,directory,*,maximum=4):
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    candidates=select_distinct_triangle_coverage(authenticated_distinct_venue_triangles(
        readiness["authenticated_pools"],limit=100),maximum=30)
    rows=[]
    for i in range(min(maximum,len(candidates))):
        path=root/("triangle-%02d.json"%i)
        try:
            status=export_three_venue(rpc,readiness,i,path)
            rows.append({"index":i,"status":status["status"],"venues":candidates[i]["route_venues"],
                         "fixture":path.name,**SAFE})
        except (ValueError,TypeError,KeyError,RuntimeError) as exc:
            rows.append({"index":i,"status":"SOURCE_FIXTURE_BLOCKED",
                         "venues":candidates[i]["route_venues"],
                         "reason":str(exc)[:240],**SAFE})
    report={"candidate_count":len(candidates),"attempted":len(rows),
            "exported":sum(row["status"]=="AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE" for row in rows),
            "routes":rows,**SAFE}
    (root/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

def offline_batch(rpc,fixtures,directory,*,observed_unix):
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    src=Path(fixtures)
    listing=json.loads((src/"summary.json").read_text())
    rows=[]
    for row in listing["routes"]:
        if row["status"]!="AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE":
            rows.append({"index":row["index"],"status":"SOURCE_FIXTURE_BLOCKED",**SAFE})
            continue
        path=src/row["fixture"]
        target=root/row["fixture"]
        result={"status":"SIGNED_TRIANGLE_BLOCKED",**SAFE}
        fixture=None
        parity=None
        economics=None
        try:
            fixture=json.loads(path.read_text())
            result=run_three_venue(rpc,fixture)
            accept(fixture,result)
            parity=compare(fixture,result,observed_unix=observed_unix)
            # Simulation does not yield an independently assessed fee or
            # authenticated SOL→start-mint conversion; report the actual blocker.
            economics=evaluate_economics(fixture,result)
        except (ValueError,TypeError,KeyError,RuntimeError) as exc:
            result["acceptance_error"]=str(exc)[:240]
        target.write_text(json.dumps(result,indent=2)+"\n")
        if parity is not None:
            (root/("parity-%02d.json"%row["index"])).write_text(json.dumps(parity,indent=2)+"\n")
        if economics is not None:
            (root/("economics-%02d.json"%row["index"])).write_text(json.dumps(economics,indent=2)+"\n")
        rows.append({"index":row["index"],"status":result["status"],
                     "route_venues":fixture.get("route_venues") if isinstance(fixture,dict) else None,
                     "observed_compute_units":result.get("positive_units_consumed"),
                     "gross_start_mint_delta":economics.get("gross_delta_start_mint_base_units") if economics else None,
                     "independent_signed_accepted":parity is not None and parity["signed_execution_accepted"],
                     "independently_validated_quote_samples":0,
                     "economics_status":economics["status"] if economics is not None else "UNAVAILABLE",
                     "quote_diagnostic_legs":len(parity["leg_comparisons"]) if parity is not None else 0,**SAFE})
    report={"attempted":len(rows),
            "independent_signed_accepted":sum(r.get("independent_signed_accepted") is True for r in rows),
            "independently_validated_quote_samples":0,"routes":rows,**SAFE}
    (root/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--mode",choices=("source","offline"),required=True)
    parser.add_argument("--rpc",default="http://127.0.0.1:8899")
    parser.add_argument("--readiness")
    parser.add_argument("--fixtures")
    parser.add_argument("--output-dir",required=True)
    parser.add_argument("--maximum",type=int,default=4)
    parser.add_argument("--observed-unix",type=int)
    a=parser.parse_args()
    if not 1<=a.maximum<=12:parser.error("maximum must be 1-12")
    if a.mode=="source":
        if not a.readiness:parser.error("source readiness required")
        result=source_batch(a.rpc,json.loads(Path(a.readiness).read_text()),a.output_dir,maximum=a.maximum)
    else:
        if not a.fixtures or a.observed_unix is None:parser.error("offline fixtures and observation timestamp required")
        result=offline_batch(a.rpc,a.fixtures,a.output_dir,observed_unix=a.observed_unix)
    print(json.dumps(result))
if __name__=="__main__":main()
