"""Classify rejected Orca accounts without promoting them to verified pools.

Reads pool and vault owners on the same Solana RPC endpoint as validation.
"""
import argparse
import json
import os
from pathlib import Path

from arb.orca_whirlpool import PROGRAM, decode, b58
from arb.rpc import call
from arb.token_vaults import TOKEN_PROGRAM
from arb.token2022_extensions import TOKEN_2022, account_observation
from arb.orca_token2022_validation import snapshot as token2022_snapshot
import base64


# Structural observations only: unknown Token-2022 extensions remain unsupported.
def observe_vault(account, expected_mint):
    owner=account.get("owner")
    raw=base64.b64decode(account["data"][0],validate=True)
    if owner not in (TOKEN_PROGRAM,TOKEN_2022) or account.get("executable") or len(raw)<165:
        raise ValueError("unsupported vault owner or truncated account")
    mint=b58(raw[:32]);authority=b58(raw[32:64])
    state=raw[108];amount=int.from_bytes(raw[64:72],"little")
    observation={"mint":mint,"mint_matches_pool":mint==expected_mint,
                 "authority":authority,"amount_base_units":amount,
                 "initialized":state==1,"account_length":len(raw),
                 "token_program":"token_2022" if owner==TOKEN_2022 else "classic"}
    decoded=account_observation(owner,raw)
    observation["extension_types"]=decoded["extension_types"]
    observation["extension_state"]="INVENTORIED_NOT_EXECUTION_AUTHENTICATED" if owner==TOKEN_2022 else "NOT_APPLICABLE"
    observation["eligible_for_executable_quote"]=False if owner==TOKEN_2022 else True
    return observation

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
        for i,acc in enumerate(accounts):
            if acc is not None:
                result["vaults"][i]["observation"]=observe_vault(
                    acc,state["token_mint_a"] if i==0 else state["token_mint_b"])
        if any(acc is None for acc in accounts):
            result["category"]="VAULT_MISSING"
        elif any(acc.get("owner")!=TOKEN_PROGRAM or acc.get("executable") for acc in accounts):
            result["category"]="VAULT_NONCLASSIC_OWNER"
            try:
                checked=token2022_snapshot(rpc,address)
                result["structural_validation"]={
                    "verified":checked["structurally_verified"],
                    "slot":checked["slot"],"mint_accounts":checked["mint_accounts"],
                    "vault_accounts":checked["vault_accounts"],
                    "actionable":False,"executable_quote":False}
            except Exception as exc:
                result["structural_validation"]={"verified":False,
                    "error":type(exc).__name__+": "+str(exc)[:140]}
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
