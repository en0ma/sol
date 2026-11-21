"""Export index candidates only when the selected DEX is an Orca label.

An Orca label is NOT proof of Token Swap v1. Local-fork authentication is
mandatory, and a dex_id should be selected from the published DEX catalog.
"""
import argparse
import json
from pathlib import Path
from arb.orca_legacy_public_index import discover,list_dexes

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    parser.add_argument("--dex-id",default=None,
                        help="explicit GeckoTerminal Solana DEX ID (never guessed)")
    parser.add_argument("--min-liquidity-usd",type=float,default=10000)
    parser.add_argument("--max-matches",type=int,default=64)
    parser.add_argument("--max-pages",type=int,default=8)
    args=parser.parse_args()
    candidates=[]
    result={"source":"GeckoTerminal Solana DEX pool index",
            "dex_id":args.dex_id,"candidate_count":0,
            "status":"NOT_CONFIGURED","onchain_verified":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False}
    try:
        catalog=list_dexes()
        if args.dex_id:
            if args.dex_id not in catalog:
                raise ValueError("selected DEX id is not in the network catalog")
            if "orca" not in ((catalog[args.dex_id] or "")+" "+args.dex_id).lower():
                raise ValueError("selected DEX does not have an Orca label")
            candidates=discover(dex_id=args.dex_id,
                                min_liquidity_usd=args.min_liquidity_usd,
                                max_matches=args.max_matches,max_pages=args.max_pages)
            result["status"]="CANDIDATES_UNVERIFIED"
        else:
            result["status"]="DEX_SELECTION_REQUIRED"
            result["orca_dex_options"]={
                key:name for key,name in catalog.items()
                if "orca" in ((name or "")+" "+key).lower()}
    except (ValueError,OSError,TimeoutError,json.JSONDecodeError) as exc:
        result["status"]="INDEX_UNAVAILABLE"
        result["error"]=str(exc)[:300]
    result["candidate_count"]=len(candidates)
    Path(args.output).write_text(json.dumps(candidates,indent=2)+"\n")
    print(json.dumps(result))

if __name__=="__main__":
    main()
