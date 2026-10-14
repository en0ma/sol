"""Fail-closed third-leg RAY->WSOL readiness for the CLMM two-hop route.

A public pool address is only a *lead*. Verify Orca program ownership,
pool mint identity, vault balances and tick-array availability on Surfpool.
No off-chain quote APIs, no transaction broadcast, and no profit claim.
"""
import base64,json,os
from arb.rpc import call
from arb.orca_whirlpool import PROGRAM as ORCA,SOL
from arb.raydium_clmm import PROGRAM as CLMM
from arb.pool_registry import refresh
from arb.whirlpool_swap import inspect_swap_requirements
RAY="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"

def probe(rpc,address):
    result={"address":address,"status":"UNVERIFIED","route_closed":False,
            "swap_simulated":False,"broadcast":False}
    try:
        account=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}]).get("value")
        if not account:raise ValueError("pool account missing")
        owner=account.get("owner")
        if owner!=ORCA:raise ValueError("candidate not an Orca Whirlpool")
        checked=refresh(rpc,[{"venue":"orca","address":address,"mints":[RAY,SOL]}])
        if checked["verified_count"]!=1:raise ValueError("pool/vault validation failed: "+str(checked["rejected"])[:180])
        pool=checked["verified_pools"][0]
        if set(pool["mints"])!={RAY,SOL}:raise ValueError("not RAY/WSOL")
        readiness=inspect_swap_requirements(rpc,address)
        direction=("a_to_b" if pool["mints"][0]==RAY else "b_to_a")
        result.update(status="POOL_VERIFIED",mints=pool["mints"],
                      verified_slot=pool["slot"],
                      direction=direction,
                      tick_arrays_available=readiness["directions"][direction]["available"])
        if result["tick_arrays_available"]:result["status"]="THIRD_LEG_READY_FOR_SIMULATION"
    except Exception as exc:
        result["error"]=type(exc).__name__+": "+str(exc)[:200]
    return result

def main():
    entries=json.load(open("arb/third_leg_candidates.json"))["candidates"]
    rpc=os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899")
    results=[probe(rpc,p["address"]) for p in entries]
    report={"status":"CANDIDATE_READY" if any(p["status"]=="THIRD_LEG_READY_FOR_SIMULATION" for p in results)
            else "NO_EXECUTABLE_THIRD_LEG","results":results,"closed_cycle_simulated":False,"profitable":False}
    print(json.dumps(report,indent=2))
    if os.environ.get("THIRD_LEG_REPORT"):
        with open(os.environ["THIRD_LEG_REPORT"],"w") as f:json.dump(report,f,indent=2)
    return 0
if __name__=="__main__":raise SystemExit(main())
