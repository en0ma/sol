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
from arb.venue_signed_quote_experiments import measure as measure_signed_quote
from arb.fixture_native_aux_inventory import inspect as inspect_native_aux
from arb.m5_three_venue_observed_economics import evaluate as evaluate_economics
from arb.m5_research_evidence_rollup import summarize as rollup
from arb.m5_source_quote_economic_gate import gate as evidence_gate
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

def offline_batch(rpc,fixtures,directory,*,observed_unix,fee_observations=None):
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    src=Path(fixtures)
    listing=json.loads((src/"summary.json").read_text())
    if fee_observations is not None and not isinstance(fee_observations,dict):
        raise ValueError("fee observations must be keyed by route index")
    rows=[]
    parity_reports=[]
    economics_reports=[]
    experimental_samples=[]
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
        evidence=None
        try:
            fixture=json.loads(path.read_text())
            result=run_three_venue(rpc,fixture)
            accept(fixture,result)
            # Auxiliary parsing is diagnostic: it must never erase a genuine
            # accepted signed execution when a fee/bin account is absent.
            try:
                native_aux=inspect_native_aux(fixture)
            except (ValueError,KeyError,TypeError) as auxiliary_error:
                native_aux={"status":"AUXILIARY_STATE_UNAVAILABLE",
                    "reason":str(auxiliary_error)[:240],**SAFE}
            (root/("native-aux-%02d.json"%row["index"])).write_text(
                json.dumps(native_aux,indent=2)+"\n")
            parity=compare(fixture,result,observed_unix=observed_unix)
            experiment=measure_signed_quote(fixture,result,observed_unix=observed_unix,parity_report=parity)
            experimental_samples.extend(experiment["venue_samples"])
            (root/("signed-price-experiment-%02d.json"%row["index"])).write_text(
                json.dumps(experiment,indent=2)+"\n")
            # Simulation does not yield an independently assessed fee or
            # authenticated SOL→start-mint conversion; report the actual blocker.
            observation=(fee_observations or {}).get(str(row["index"]))
            economics=evaluate_economics(fixture,result,fee_observation=observation)
            evidence=evidence_gate(fixture,result,parity,economics)
        except (ValueError,TypeError,KeyError,RuntimeError) as exc:
            result["acceptance_error"]=str(exc)[:240]
        target.write_text(json.dumps(result,indent=2)+"\n")
        if parity is not None:
            parity_reports.append(parity)
            (root/("parity-%02d.json"%row["index"])).write_text(json.dumps(parity,indent=2)+"\n")
        if evidence is not None:
            (root/("evidence-%02d.json"%row["index"])).write_text(json.dumps(evidence,indent=2)+"\n")
        if economics is not None:
            economics_reports.append(economics)
            (root/("economics-%02d.json"%row["index"])).write_text(json.dumps(economics,indent=2)+"\n")
        rows.append({"index":row["index"],"status":result["status"],
                     "route_venues":fixture.get("route_venues") if isinstance(fixture,dict) else None,
                     "observed_compute_units":result.get("positive_units_consumed"),
                     "gross_start_mint_delta":economics.get("gross_delta_start_mint_base_units") if economics else None,
                     "break_even_total_cost_budget_start_mint_base_units":economics.get("maximum_affordable_total_cost_start_mint_base_units") if economics else None,
                     "signed_quote_leg_count":parity.get("quoted_leg_count",0) if parity else 0,
                     "signed_quote_blocked_leg_count":parity.get("blocked_leg_count",0) if parity else 0,
                     "independent_signed_accepted":parity is not None and parity["signed_execution_accepted"],
                     "independently_validated_quote_samples":0,
                     "economics_status":economics["status"] if economics is not None else "UNAVAILABLE",
                     "source_price_economics_gate":evidence["status"] if evidence is not None else "UNAVAILABLE",
                     "quote_diagnostic_legs":len(parity["leg_comparisons"]) if parity is not None else 0,**SAFE})
    report={"attempted":len(rows),
            "independent_signed_accepted":sum(r.get("independent_signed_accepted") is True for r in rows),
            "independently_validated_quote_samples":0,"routes":rows,**SAFE}
    report["observed_venue_quote_samples"]=sum(
        s["sample_status"]=="SIGNED_FORK_QUOTE_COMPARISON" for s in experimental_samples)
    report["observed_venue_quote_exact_matches"]=sum(
        s["exact_integer_match"] is True for s in experimental_samples)
    report["observed_venue_quote_mismatches"]=sum(
        s["exact_integer_match"] is False for s in experimental_samples)
    by_venue={}
    for sample in experimental_samples:
        venue=sample["venue"]
        summary=by_venue.setdefault(venue,{"compared":0,"exact":0,"blocked":0,"mismatch":0,
            "maximum_absolute_error_base_units":None})
        if sample["sample_status"]!="SIGNED_FORK_QUOTE_COMPARISON":
            summary["blocked"]+=1
        else:
            summary["compared"]+=1
            summary["exact" if sample["exact_integer_match"] else "mismatch"]+=1
            error=sample["absolute_integer_error_base_units"]
            if (summary["maximum_absolute_error_base_units"] is None or
                    error>summary["maximum_absolute_error_base_units"]):
                summary["maximum_absolute_error_base_units"]=error
    report["signed_price_evidence_by_venue"]=by_venue
    (root/"signed-price-experiments.json").write_text(json.dumps(
        {"samples":experimental_samples,"by_venue":by_venue,**SAFE},indent=2)+"\n")
    evidence=rollup(listing,report,parity_reports,economics_reports)
    (root/"evidence-rollup.json").write_text(json.dumps(evidence,indent=2)+"\n")
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
    parser.add_argument("--fee-observations")
    a=parser.parse_args()
    if not 1<=a.maximum<=12:parser.error("maximum must be 1-12")
    if a.mode=="source":
        if not a.readiness:parser.error("source readiness required")
        result=source_batch(a.rpc,json.loads(Path(a.readiness).read_text()),a.output_dir,maximum=a.maximum)
    else:
        if not a.fixtures or a.observed_unix is None:parser.error("offline fixtures and observation timestamp required")
        observation_map=json.loads(Path(a.fee_observations).read_text()) if a.fee_observations else None
        result=offline_batch(a.rpc,a.fixtures,a.output_dir,
            observed_unix=a.observed_unix,fee_observations=observation_map)
    print(json.dumps(result))
if __name__=="__main__":main()
