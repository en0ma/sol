"""Diagnose a published Raydium CPMM address via Surfpool RPC only.

Account's actual mints and vaults, not upstream SDK text, decide eligibility.
No external DEX APIs; candidate is not automatically pinned or asserted valid.
"""
import argparse,base64,json,os
from arb.rpc import call
from arb.raydium_cpmm import PROGRAM,decode,verify_vaults
from arb.orca_whirlpool import SOL,USDC
DEFAULT_CANDIDATE="7JuwJuNU88gurFnyWeiyGKbFmExMWcmRZntn9imEzdny"

def inspect(rpc,address):
    reply=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}])
    info=reply.get("value")
    result={"address":address,"pool_exists":info is not None,
            "verified_sol_usdc":False,"cross_venue_simulated":False}
    if not info:return {**result,"status":"MISSING"}
    result["owner"]=info.get("owner")
    if info.get("owner")!=PROGRAM or info.get("executable"):
        return {**result,"status":"WRONG_PROGRAM"}
    state=decode(base64.b64decode(info["data"][0],validate=True))
    result.update({"token_0_mint":state["token_0_mint"],"token_1_mint":state["token_1_mint"],
                   "swap_enabled":state["swap_enabled"]})
    if {state["token_0_mint"],state["token_1_mint"]}!={SOL,USDC}:
        return {**result,"status":"NOT_SOL_USDC"}
    try:
        verified=verify_vaults(rpc,address,state)
    except ValueError as exc:
        return {**result,"status":"FAILED_VAULT_VERIFICATION","reason":str(exc)}
    result.update(verified)
    result["status"]="VERIFIED_SOL_USDC"
    result["verified_sol_usdc"]=True
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--address",default=DEFAULT_CANDIDATE)
    parser.add_argument("--output",default=os.environ.get("RAYDIUM_CANDIDATE_REPORT",""))
    a=parser.parse_args()
    result=inspect(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),a.address)
    print(json.dumps(result,indent=2))
    if a.output:
        with open(a.output,"w") as f:json.dump(result,f,indent=2)
    return 0  # diagnostic: does not claim successful swaps or pool compatibility
if __name__=="__main__":
    raise SystemExit(main())
