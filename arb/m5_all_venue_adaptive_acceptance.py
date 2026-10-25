"""A separate, strict adaptive-amount acceptance for every ordered venue pair.

Never count legacy two-instruction atomic evidence as adaptive success.
"""
import argparse
import json
from pathlib import Path
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
    return {"status":"SEVEN_VENUE_ADAPTIVE_RESEARCH","target":len(routes),
            "verified":verified,"routes":rows,
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
    print(json.dumps({"adaptive_verified":result["verified"],"target":result["target"],**SAFE}))
    return 0 if result["verified"]==result["target"] else 1
if __name__=="__main__":raise SystemExit(main())
