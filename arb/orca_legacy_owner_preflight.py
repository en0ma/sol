"""Read-only batched ownership preflight for indexed Orca legacy candidates.

API pool labels are not protocol evidence. A batch of local-fork account reads
filters candidates to the exact SPL Token Swap v1 program before expensive
state/vault authentication. This never signs, simulates or broadcasts.
"""
import argparse
import json
from pathlib import Path
from arb.rpc import call
from arb.pumpswap_local_simulation import local_rpc_only

ORCA_TOKEN_SWAP_V1="DjVE6JNiYqPL2QXyCUUh8rNjHrbz9hXHNYt99MQ59qw1"
MAX_INPUT=64
MAX_OUTPUT=16

def preflight(rpc,addresses):
    local_rpc_only(rpc)
    if (not isinstance(addresses,list) or len(addresses)>MAX_INPUT
            or any(not isinstance(a,str) or not 32<=len(a)<=44 for a in addresses)):
        raise ValueError("invalid bounded Orca index candidates")
    unique=list(dict.fromkeys(addresses))
    if not unique:
        return {"status":"NO_INDEX_CANDIDATES","matching_program":[],"checked":0,
                "mismatched_owner":0,"missing":0,
                "actionable":False,"live_execution_approved":False,"broadcast":False}
    response=call(rpc,"getMultipleAccounts",[
        unique,{"encoding":"base64","commitment":"confirmed"}])
    accounts=response.get("value") if isinstance(response,dict) else None
    if not isinstance(accounts,list) or len(accounts)!=len(unique):
        raise ValueError("incomplete Orca index owner preflight")
    matching=[]
    mismatch=missing=0
    for address,account in zip(unique,accounts):
        if account is None:
            missing+=1
        elif not isinstance(account,dict):
            raise ValueError("malformed Orca index account")
        elif account.get("owner")==ORCA_TOKEN_SWAP_V1 and account.get("executable") is False:
            matching.append(address)
        else:
            mismatch+=1
    return {"status":"PROGRAM_OWNER_CANDIDATES_ONLY",
            "matching_program":matching[:MAX_OUTPUT],
            "matching_program_total":len(matching),
            "checked":len(unique),"mismatched_owner":mismatch,"missing":missing,
            "truncated":len(matching)>MAX_OUTPUT,
            "onchain_pool_decoder_verified":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--rpc",default="http://127.0.0.1:8899")
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--report",required=True)
    args=parser.parse_args()
    report=preflight(args.rpc,json.loads(Path(args.input).read_text()))
    Path(args.output).write_text(json.dumps(report["matching_program"],indent=2)+"\n")
    Path(args.report).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({key:value for key,value in report.items()
                      if key!="matching_program"}))

if __name__=="__main__":
    main()
