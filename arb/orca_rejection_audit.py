"""Classify rejected Orca accounts without promoting them to verified pools.

Reads pool and vault owners on the same Solana RPC endpoint as validation.
"""
import argparse
import json
import os
from pathlib import Path

from arb.orca_whirlpool import PROGRAM, decode
from arb.rpc import call
from arb.token_vaults import TOKEN_PROGRAM
import base64

# Non-classic owners are reported, never accepted as verified.

def classify(rpc,address):
    result={"address":address,"verified":False,"actionable":False}
    try:
        response=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}])
        pool=response.get("value")
        result["pool_owner"]=pool.get("owner") if isinstance(pool,dict) else None
        if pool is None:
            result["category"]="POOL_MISSING"
            return result
        if pool.get("owner")!=PROGRAM or pool.get("executable"):
            result["category"]="POOL_OWNER_MISMATCH"
            return result
        state=decode(base64.b64decode(pool["data"][0],validate=True))
        vaults=[state["token_vault_a"],state["token_vault_b"]]
        snapshot=call(rpc,"getMultipleAccounts",[vaults,{"encoding":"base64","commitment":"confirmed"}])
        accounts=snapshot.get("value")
        result["slot"]=snapshot.get("context",{}).get("slot")
        if not isinstance(accounts,list) or len(accounts)!=2 or not isinstance(result["slot"],int):
            result["category"]="SNAPSHOT_UNAVAILABLE"
            return result
        result["vaults"]=[{"address":addr,"owner":acc.get("owner") if isinstance(acc,dict) else None,
                            "exists":acc is not None}
                           for addr,acc in zip(vaults,accounts)]
        if any(acc is None for acc in accounts):
            result["category"]="VAULT_MISSING"
        elif any(acc.get("owner")!=TOKEN_PROGRAM or acc.get("executable") for acc in accounts):
            result["category"]="VAULT_NONCLASSIC_OWNER"
        else:
            result["category"]="CLASSIC_VAULTS_PRESENT_RETRY_FULL_VALIDATION"
    except Exception as exc:
        result["category"]="AUDIT_ERROR"
        result["error"]=type(exc).__name__+": "+str(exc)[:150]
    return result

def audit(rpc,report,limit=50):
    if type(limit) is not int or not 1<=limit<=200:
        raise ValueError("invalid audit budget")
    rows=report.get("rejections")
    if not isinstance(rows,list):
        raise ValueError("missing rejected candidate list")
    selected=[e["address"] for e in rows if isinstance(e,dict)
              and e.get("venue")=="orca" and isinstance(e.get("address"),str)]
    result=[classify(rpc,address) for address in selected[:limit]]
    return {"audited":len(result),"total_rejections":len(rows),"results":result,
            "verified_count":0,"actionable":False,"mainnet_broadcast":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--limit",type=int,default=50)
    args=p.parse_args()
    report=audit(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                 json.loads(Path(args.input).read_text()),args.limit)
    Path(args.output).write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!="results"},indent=2))

if __name__=="__main__":
    main()
