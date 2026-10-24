"""Bounded fork-only cross-venue size sweep and conservative opportunity filter."""
import json,os
from arb.cross_venue import run

SIZES=(1000,10000,50000,75000,100000)
MIN_PROFIT_LAMPORTS=10000

def evaluate(result,min_profit=MIN_PROFIT_LAMPORTS):
    if type(min_profit) is not int or min_profit<=0:raise ValueError("invalid min profit")
    pnl=result.get("net_wsol_change_lamports")
    inventory=result.get("residual_usdc_base_units")
    eligible=(result.get("cross_venue_success") is True and
              type(pnl) is int and type(inventory) is int and inventory==0 and
              result.get("venues_executed")==2 and
              result.get("simulation_did_not_persist") is True and
              result.get("signed_simulation_requested") is True and pnl>=min_profit)
    if eligible: reason="SIMULATED_NET_PROFIT"
    elif result.get("cross_venue_success") is not True: reason="SWAP_FAILED_OR_UNCLOSED"
    elif type(inventory) is not int or inventory!=0: reason="RESIDUAL_INTERMEDIATE_TOKEN"
    elif result.get("simulation_did_not_persist") is not True or result.get("signed_simulation_requested") is not True: reason="SIMULATION_ISOLATION_UNVERIFIED"
    elif type(pnl) is not int: reason="MISSING_NETWORK_FEE"
    elif pnl<min_profit: reason="BELOW_MINIMUM_NET_PROFIT"
    else: reason="INELIGIBLE"
    return {"status":"CANDIDATE" if eligible else "REJECTED",
            "simulated_profitable":eligible,
            "live_execution_approved":False,
            "net_wsol_change_lamports":pnl if type(pnl) is int else None,
            "reason":reason}

def sweep(rpc,orca,raydium,sizes=SIZES,max_wsol=1000000,reverse=False):
    if (not sizes or len(sizes)>8 or any(type(x)is not int or x<=0 or x>100000
                                         for x in sizes) or len(set(sizes))!=len(sizes)):
        raise ValueError("invalid bounded sizes")
    reports=[]
    for size in sizes:
        simulated=run(rpc,orca,raydium,max_wsol,size,reverse=reverse)
        reports.append({"usdc_amount_base_units":size,
                        "simulation":{k:v for k,v in simulated.items() if k!="log_tail"},
                        "decision":evaluate(simulated)})
    successful=[r for r in reports if r["simulation"].get("cross_venue_success") and
                type(r["simulation"].get("net_wsol_change_lamports")) is int]
    best=max(successful,key=lambda r:r["simulation"]["net_wsol_change_lamports"]) if successful else None
    return {"best_simulated_size_usdc_base_units":best["usdc_amount_base_units"] if best else None,
            "best_net_wsol_change_lamports":best["simulation"]["net_wsol_change_lamports"] if best else None,
            "direction":"raydium_to_orca" if reverse else "orca_to_raydium",
            "status":"PASS" if len(reports)==len(sizes) else "INCOMPLETE",
            "evaluated":len(reports),"profitable_candidates":sum(
                r["decision"]["simulated_profitable"] for r in reports),
            "live_execution_approved":False,"results":reports}

def main():
    with open("arb/whirlpool_pools.json") as f:orca=json.load(f)["pools"][0]["address"]
    with open("arb/raydium_cpmm_pools.json") as f:raydium=json.load(f)["pools"][0]["address"]
    result=sweep(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),orca,raydium,
                 reverse=os.environ.get("CROSS_VENUE_REVERSE")=="1")
    print(json.dumps(result,indent=2))
    if os.environ.get("CROSS_VENUE_SWEEP_REPORT"):
        with open(os.environ["CROSS_VENUE_SWEEP_REPORT"],"w") as f:json.dump(result,f,indent=2)
    # Unprofitable routes are expected outcomes, not test failures.
    return 0 if result["status"]=="PASS" else 1

if __name__=="__main__":raise SystemExit(main())
