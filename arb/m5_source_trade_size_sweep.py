"""Bounded actual native-quote size sweep over authenticated fixture manifest.

Do not infer executable profit from a quoted gross spread.
"""
from arb.m5_existing_source_research import evaluate

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def sweep(source_dir, *, sizes, observed_unix, maximum=30):
    if (not isinstance(sizes,list) or not 1<=len(sizes)<=8 or
            len(set(sizes))!=len(sizes) or any(type(s)is not int or not 0<s<2**64 for s in sizes)):
        raise ValueError("1..8 distinct positive base-unit trade sizes required")
    observations=[{"amount_in_base_units":size,**evaluate(source_dir,
                   amount_in=size,observed_unix=observed_unix,maximum=maximum)}
                  for size in sizes]
    shortlisted=[]
    for observation in observations:
        for row in observation["ranked_routes"]:
            if row.get("gross_delta_start_mint_base_units",0)>0:
                shortlisted.append({
                    "amount_in_base_units":observation["amount_in_base_units"],
                    "source_batch_route_index":row["source_batch_route_index"],
                    "start_mint":row.get("start_mint"),
                    "gross_delta_start_mint_base_units":row["gross_delta_start_mint_base_units"],
                    "net_profit_verified":False,**SAFE})
    shortlisted.sort(key=lambda x:x["gross_delta_start_mint_base_units"],reverse=True)
    return {"status":"SOURCE_AUTHENTICATED_MULTI_SIZE_GROSS_SWEEP",
            "sizes":sizes,"size_results":observations,
            "total_native_fully_quoted":sum(r["native_fully_quoted"] for r in observations),
            "total_native_quote_blocked":sum(r["native_quote_blocked"] for r in observations),
            "total_positive_gross_indicative":sum(r["positive_gross_indicative"] for r in observations),
            "gross_positive_shortlist":shortlisted[:maximum],
            "net_profitable_opportunities_verified":0,**SAFE}

def main():
    import argparse,json
    from pathlib import Path
    p=argparse.ArgumentParser()
    p.add_argument("--source-dir",required=True)
    p.add_argument("--sizes",required=True,help="comma separated start-mint base units")
    p.add_argument("--observed-unix",required=True,type=int)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    out=sweep(a.source_dir,sizes=[int(s) for s in a.sizes.split(",")],
              observed_unix=a.observed_unix)
    Path(a.output).write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({k:out[k] for k in ("status","sizes","total_native_fully_quoted",
        "total_native_quote_blocked","total_positive_gross_indicative","broadcast")}))
if __name__=="__main__":main()
