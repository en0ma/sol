"""Fetch Raydium API candidates before local-only fork authentication."""
import argparse
import json
from pathlib import Path
from arb.raydium_public_pool_discovery import discover

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    parser.add_argument("--min-liquidity-usd",type=float,default=10000)
    parser.add_argument("--max-pages",type=int,default=5)
    args=parser.parse_args()
    try:
        addresses=discover(min_liquidity_usd=args.min_liquidity_usd,
                           max_pages=args.max_pages,max_matches=16)
    except (ValueError,OSError,TimeoutError,json.JSONDecodeError) as exc:
        print("Raydium public discovery unavailable: "+str(exc))
        addresses=[]
    Path(args.output).write_text(json.dumps(addresses,indent=2)+"\n")
    print(json.dumps({"source":"Raydium API v3","candidate_count":len(addresses),
                      "min_liquidity_usd":args.min_liquidity_usd,
                      "onchain_verified":False,"broadcast":False}))

if __name__=="__main__":
    main()
