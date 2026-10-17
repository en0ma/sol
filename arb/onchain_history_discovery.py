"""Bounded on-chain transaction-history pool identity discovery.

Reads signatures on verified DEX program accounts and account keys from
confirmed transactions. Every candidate is decoded via getAccountInfo and
re-verified with vault checks before reporting. No heuristic log text parsing,
DEX HTTP APIs, or broadcasts. Program history is only a seed, not an index.
"""
import argparse,base64,json,os
from arb.rpc import call
from arb.onchain_pool_discovery import VENUES,verify

def discover_history(rpc,venues=("orca","raydium_cpmm"),signature_limit=5,max_keys=120):
    if any(v not in VENUES for v in venues) or not 1<=signature_limit<=20:
        raise ValueError("invalid history scope")
    if not 1<=max_keys<=500:raise ValueError("invalid key budget")
    pools={};errors=[];scanned=0
    for venue in venues:
        program,_,_,_,decoder=VENUES[venue]
        try:
            signatures=call(rpc,"getSignaturesForAddress",[program,{"limit":signature_limit}])
            if not isinstance(signatures,list):raise ValueError("unexpected signatures")
        except Exception as exc:
            errors.append({"venue":venue,"stage":"signatures","error":str(exc)[:180]});continue
        keys=set()
        for sig in signatures:
            try:
                transaction=call(rpc,"getTransaction",[sig["signature"],{
                    "encoding":"json","commitment":"confirmed",
                    "maxSupportedTransactionVersion":0}])
                if transaction is None:continue
                message=transaction["transaction"]["message"]
                for address in message.get("accountKeys",[]):
                    if isinstance(address,str):keys.add(address)
            except Exception as exc:
                errors.append({"venue":venue,"stage":"transaction","error":str(exc)[:180]})
        for address in sorted(keys):
            if scanned>=max_keys:break
            scanned+=1
            try:
                account=call(rpc,"getAccountInfo",[address,{"encoding":"base64",
                                                    "commitment":"confirmed"}]).get("value")
                if not account or account.get("owner")!=program:continue
                raw=base64.b64decode(account["data"][0],validate=True)
                state=decoder(raw)
                validated=verify(rpc,venue,address,state)
                pools[(venue,address)]=validated
            except ValueError:
                continue  # Most transaction account keys are not pool accounts.
            except Exception as exc:
                errors.append({"venue":venue,"stage":"account","error":str(exc)[:180]})
        if scanned>=max_keys:break
    return {"status":"COMPLETE" if not errors else "PARTIAL",
            "pools":list(pools.values()),"verified_count":len(pools),
            "transaction_keys_checked":scanned,"errors":errors,
            "route_simulated":False,"broadcast":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--venues",default="orca,raydium_cpmm")
    parser.add_argument("--signatures",type=int,default=5)
    parser.add_argument("--output",default=os.environ.get("DEX_HISTORY_REPORT",""))
    args=parser.parse_args()
    venues=tuple(x.strip() for x in args.venues.split(","))
    report=discover_history(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                            venues,args.signatures)
    print(json.dumps(report,indent=2))
    if args.output:
        with open(args.output,"w") as f:json.dump(report,f,indent=2)
    return 0 if report["status"]=="COMPLETE" else 2
if __name__=="__main__":raise SystemExit(main())
