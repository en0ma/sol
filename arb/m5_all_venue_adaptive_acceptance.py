"""A separate, strict adaptive-amount acceptance for every ordered venue pair.

Never count legacy two-instruction atomic evidence as adaptive success.
"""
import argparse
import json
from pathlib import Path
from collections import Counter
from arb.m5_adaptive_signed_acceptance import check
from arb.next_ten_atomic_routes import route_batch
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def audit(root,*,batch="remaining",only_venue=None):
    routes=tuple(route for route in route_batch(batch) if only_venue is None or only_venue in route)
    if not routes:
        raise ValueError("adaptive route selection empty")
    rows=[]
    for route in routes:
        path=Path(root)/("__".join(route)+".json")
        if not path.is_file():
            rows.append({"route":"__".join(route),"status":"UNVERIFIED",
                         "failure_reasons":["signed adaptive receipt missing"],**SAFE})
            continue
        try:
            rows.append(check(route,json.loads(path.read_text())))
        except (ValueError,TypeError,KeyError,OSError) as exc:
            rows.append({"route":"__".join(route),"status":"UNVERIFIED",
                         "failure_reasons":["invalid adaptive receipt: "+str(exc)[:160]],**SAFE})
    verified=sum(x["status"]=="VERIFIED_ADAPTIVE_SIGNED_OFFLINE" for x in rows)
    failures=[{"route":r["route"],"failure_reasons":r["failure_reasons"]}
              for r in rows if r["status"]!="VERIFIED_ADAPTIVE_SIGNED_OFFLINE"]
    failure_counts=Counter(reason for r in failures for reason in r["failure_reasons"])
    failing_venue_occurrences=Counter(venue for r in failures for venue in r["route"].split("__"))
    dlmm_affected=[r["route"] for r in failures if "meteora_dlmm" in r["route"].split("__")]
    venue_totals=Counter(venue for route in routes for venue in route)
    if any(r.get("route") not in {"__".join(route) for route in routes} for r in rows):
        raise ValueError("adaptive signed audit row route identity mismatch")
    venue_verified=Counter(venue for r in rows if r["status"]=="VERIFIED_ADAPTIVE_SIGNED_OFFLINE"
                           for venue in r["route"].split("__"))
    venue_coverage={venue:{"attempted_route_occurrences":count,
                           "verified_route_occurrences":venue_verified[venue],
                           "unverified_route_occurrences":failing_venue_occurrences[venue]}
                    for venue,count in sorted(venue_totals.items())}
    # Explicitly distinguish actual independent signed research from any
    # hypothetical source quote or complete economic verification.
    signed_complete=(verified==len(routes))
    if verified+len(failures)!=len(routes):
        raise ValueError("adaptive source route verification partition invalid")
    if any(row["attempted_route_occurrences"]!=row["verified_route_occurrences"]+row["unverified_route_occurrences"]
           for row in venue_coverage.values()):
        raise ValueError("adaptive per-venue signed coverage partition invalid")
    return {"status":"SEVEN_VENUE_ADAPTIVE_RESEARCH","target":len(routes),
            "unverified_route_count":len(failures),
            "unverified_routes":failures,
            "failure_reason_counts":dict(sorted(failure_counts.items())),
            "failing_venue_occurrences":dict(sorted(failing_venue_occurrences.items())),
            "dlmm_unverified_routes":dlmm_affected,
            "venue_signed_coverage":venue_coverage,
            "verified":verified,"routes":rows,
            "all_selected_signed_routes_verified":signed_complete,
            "complete_native_route_quotes_verified":0,
            "net_profitable_routes_verified":0,
            "full_42_adaptive_verified":False,
            "independently_validated_quote_samples":0,**SAFE}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--receipts",type=Path,required=True)
    p.add_argument("--only-venue",choices=("raydium_amm_v4",))
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--batch",choices=("first","next","remaining","non-v4"),default="remaining")
    args=p.parse_args()
    result=audit(args.receipts,batch=args.batch,only_venue=args.only_venue)
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"adaptive_verified":result["verified"],"target":result["target"],
                      "unverified_routes":result["unverified_routes"],
                      "failure_reason_counts":result["failure_reason_counts"],
                      "failing_venue_occurrences":result["failing_venue_occurrences"],
                      "dlmm_unverified_routes":result["dlmm_unverified_routes"],
                      "venue_signed_coverage":result["venue_signed_coverage"],**SAFE}))
    return 0 if result["verified"]==result["target"] else 1
if __name__=="__main__":raise SystemExit(main())
