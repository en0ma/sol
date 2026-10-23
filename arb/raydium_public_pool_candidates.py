"""Fetch Raydium API candidates before local-only fork authentication."""
import argparse
import json
from pathlib import Path
from arb.raydium_public_pool_discovery import discover

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    try:
        addresses=discover()
    except (ValueError,OSError,TimeoutError,json.JSONDecodeError) as exc:
        print("Raydium public discovery unavailable: "+str(exc))
        addresses=[]
    Path(args.output).write_text(json.dumps(addresses,indent=2)+"\n")
    print(json.dumps({"source":"Raydium API v3","candidate_count":len(addresses),
                      "onchain_verified":False,"broadcast":False}))

if __name__=="__main__":
    main()
