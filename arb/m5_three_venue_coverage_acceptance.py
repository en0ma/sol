"""Strict evidence audit of multi-venue signed route batch acceptance counts."""
import json,sys
from pathlib import Path
from arb.m5_three_distinct_venue_signed_acceptance import verify
from arb.m5_three_venue_signed_quote_parity import compare
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def check(source_dir,receipt_dir,*,minimum_unique=3,observed_unix=0):
    src=Path(source_dir);dst=Path(receipt_dir)
    index=json.loads((src/"summary.json").read_text())
    summary=json.loads((dst/"summary.json").read_text())
    accepted=[];errors=[]
    for item in index["routes"]:
        if item["status"]!="AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE":continue
        filename=item["fixture"]
        try:
            fixture=json.loads((src/filename).read_text())
            receipt=json.loads((dst/filename).read_text())
            verify(fixture,receipt)
            report=compare(fixture,receipt,observed_unix=observed_unix)
            if report["signed_execution_accepted"] is not True:raise ValueError("comparison rejected receipt")
            accepted.append({"index":item["index"],"venues":fixture["route_venues"],
                             "pool_addresses":fixture["route_pool_addresses"],
                             "quoted_leg_diagnostics":len(report["leg_comparisons"]),**SAFE})
        except (ValueError,KeyError,TypeError,OSError) as exc:
            errors.append({"index":item["index"],"reason":str(exc)[:180]})
    unique={tuple(sorted(row["venues"])) for row in accepted}
    if len(accepted)!=summary["independent_signed_accepted"]:
        raise ValueError("claimed accepted count diverges from independently verified receipts")
    return {"status":"MULTI_VENUE_COVERAGE_ACCEPTED" if len(unique)>=minimum_unique else "INSUFFICIENT_DISTINCT_SIGNED_VENUE_COMBINATIONS",
        "distinct_venue_triples":len(unique),"accepted_receipts":len(accepted),
        "minimum_required":minimum_unique,"accepted_routes":accepted,"rejected":errors,
        "independently_validated_quote_samples":0,**SAFE}
def main():
    if len(sys.argv)!=5:raise SystemExit("usage: source_dir receipt_dir min_distinct observed_unix")
    r=check(sys.argv[1],sys.argv[2],minimum_unique=int(sys.argv[3]),observed_unix=int(sys.argv[4]))
    print(json.dumps(r))
    if r["status"]!="MULTI_VENUE_COVERAGE_ACCEPTED":raise SystemExit(1)
if __name__=="__main__":main()
