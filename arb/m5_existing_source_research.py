"""Research assessment of actual signed source-batch artifacts, without replay.

Reuses existing authenticated source fixtures, source-bound native quotes, and
independently assessed signed receipts. No RPC, signing or broadcasting.
"""
import json
from pathlib import Path
from arb.m5_source_triangle_quote_ranking import rank
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def evaluate(source_dir, *, amount_in, observed_unix, signed_dir=None, maximum=30):
    src=Path(source_dir)
    listing=json.loads((src/"summary.json").read_text())
    if any(listing.get(k) is not False for k in SAFE):
        raise ValueError("unsafe source summary")
    records=listing.get("routes")
    if not isinstance(records,list) or len(records)>100:
        raise ValueError("invalid bounded source manifest")
    fixtures=[];mapping=[]
    for row in records:
        if row.get("status")!="AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE":
            continue
        path=row.get("fixture")
        if (not isinstance(path,str) or not path.startswith("triangle-")
                or "/" in path or "\\" in path or not path.endswith(".json")):
            raise ValueError("invalid source fixture path")
        fixtures.append(json.loads((src/path).read_text()))
        mapping.append(row["index"])
    quoted=rank(fixtures,amount_in=amount_in,observed_unix=observed_unix,maximum=maximum)
    by_source={}
    for row in quoted["all_results"]:
        source_index=mapping[row["index"]]
        row["source_batch_route_index"]=source_index
        by_source[source_index]=row
    signed_records={}
    if signed_dir is not None:
        signed=json.loads((Path(signed_dir)/"summary.json").read_text())
        if any(signed.get(k) is not False for k in SAFE):
            raise ValueError("unsafe signed summary")
        for row in signed.get("routes",[]):
            index=row.get("index")
            if type(index)is not int or index in signed_records or index not in set(mapping):
                raise ValueError("unmatched or duplicate signed route")
            signed_records[index]=row
    ranked=[]
    signed_gross_sign_disagreements=0
    for row in quoted["ranked"]:
        index=mapping[row["index"]]
        row={**row,"source_batch_route_index":index}
        receipt=signed_records.get(index)
        signed_delta=receipt.get("gross_start_mint_delta") if receipt else None
        signed_accepted=receipt is not None and receipt.get("independent_signed_accepted") is True
        if signed_accepted and type(signed_delta) is int:
            if (signed_delta>0)!=(row["gross_delta_start_mint_base_units"]>0):
                signed_gross_sign_disagreements+=1
        ranked.append({**row,
            "signed_minus_quoted_gross_base_units":(
                signed_delta-row["gross_delta_start_mint_base_units"]
                if signed_accepted and type(signed_delta) is int else None),
            "signed_observation":({
                "status":receipt.get("status"),
                "independent_signed_accepted":receipt.get("independent_signed_accepted") is True,
                "gross_start_mint_delta":receipt.get("gross_start_mint_delta"),
                "economics_status":receipt.get("economics_status"),
                "source_price_economics_gate":receipt.get("source_price_economics_gate"),
            } if receipt else {"status":"NOT_OBSERVED",
                              "independent_signed_accepted":False}),
            **SAFE})
    return {"status":"SOURCE_BOUND_RESEARCH_NO_NET_PROFIT_CLAIM",
        "source_exported":len(fixtures),"native_fully_quoted":quoted["fully_quoted"],
        "native_quote_blocked":quoted["blocked"],
        "positive_gross_indicative":quoted["positive_gross"],
        "signed_receipts_available":len(signed_records),
        "signed_gross_sign_disagreements":signed_gross_sign_disagreements,
        "ranked_routes":ranked,"all_native_quote_results":quoted["all_results"],
        "net_profit_verified":False,"broadcast":False,**SAFE}

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--source-dir",required=True)
    p.add_argument("--signed-dir")
    p.add_argument("--amount-in",type=int,required=True)
    p.add_argument("--observed-unix",type=int,required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    report=evaluate(a.source_dir,amount_in=a.amount_in,
        observed_unix=a.observed_unix,signed_dir=a.signed_dir)
    Path(a.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in ("status","source_exported",
        "native_fully_quoted","native_quote_blocked",
        "positive_gross_indicative","signed_receipts_available","broadcast")}))

if __name__=="__main__":
    main()
