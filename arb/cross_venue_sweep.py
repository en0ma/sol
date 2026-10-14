"""Bounded fork-only cross-venue size sweep and conservative opportunity filter."""
import json,os
from arb.cross_venue import run

SIZES=(1000,10000,50000)
MIN_PROFIT_LAMPORTS=10000

def evaluate(result,min_profit=MIN_PROFIT_LAMPORTS):
    if type(min_profit) is not int or min_profit<=0:raise ValueError("invalid min profit")
    pnl=result.get("net_wsol_change_lamports")
    inventory=result.get("residual_usdc_base_units")
    eligible=(result.get("cross_venue_success") is True and
              type(pnl) is int and type(inventory) is int and inventory==0 and
              result.get("venues_executed")==2 and pnl>=min_profit)
    return {"status":"CANDIDATE" if eligible else "REJECTED",
            "simulated_profitable":eligible,
            "live_execution_approved":False,
            "net_wsol_change_lamports":pnl if type(pnl) is int else None,
            "reason":("SIMULATED_NET_PROFIT" if eligible else
                      "MISSING_NET_FEE_OR_LOSS_OR_INCOMPLETE_ROUTE")}

def sweep(rpc,orca,raydium,sizes=SIZES,max_wsol=1000000):
    if (not sizes or len(sizes)>8 or any(type(x)is not int or x<=0 or x>100000
                                         for x in sizes) or len(set(sizes))!=len(sizes)):
        raise ValueError("invalid bounded sizes")
    reports=[]
    for size in sizes:
        simulated=run(rpc,orca,raydium,max_wsol,size)
        reports.append({"usdc_amount_base_units":size,
                        "simulation":{k:v for k,v in simulated.items() if k!="log_tail"},
                        "decision":evaluate(simulated)})
    return {"status":"PASS" if len(reports)==len(sizes) else "INCOMPLETE",
            "evaluated":len(reports),"profitable_candidates":sum(
                r["decision"]["simulated_profitable"] for r in reports),
            "live_execution_approved":False,"results":reports}

def main():
    with open("arb/whirlpool_pools.json") as f:orca=json.load(f)["pools"][0]["address"]
    with open("arb/raydium_cpmm_pools.json") as f:raydium=json.load(f)["pools"][0]["address"]
    result=sweep(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),orca,raydium)
    print(json.dumps(result,indent=2))
    if os.environ.get("CROSS_VENUE_SWEEP_REPORT"):
        with open(os.environ["CROSS_VENUE_SWEEP_REPORT"],"w") as f:json.dump(result,f,indent=2)
    # Unprofitable routes are expected outcomes, not test failures.
    return 0 if result["status"]=="PASS" and all(
        r["simulation"].get("cross_venue_success") for r in result["results"]) else 1

if __name__=="__main__":raise SystemExit(main())
