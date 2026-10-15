"""Fail-closed amount-aware screening of discovered multi-pool arbitrage cycles.

Only verified Raydium CPMM legs can currently be priced with reserve math
and verified on-chain fee configs. Other venues remain explicitly unquoted.
All amounts are SPL token base units; no assumed decimal conversions.
"""
import json,os
from arb.pool_registry import refresh
from arb.opportunity_graph import cycles
from arb.cpmm_quote import quote_pool
from arb.cpmm_config import read_pool_config

def score_cycle(route,pool_index,fee_index,input_amount,network_fee=None):
    if type(input_amount)is not int or input_amount<=0:raise ValueError("invalid input size")
    if network_fee is not None and (type(network_fee)is not int or network_fee<0):
        raise ValueError("invalid network fee")
    amount=input_amount
    legs=[]
    for leg in route["legs"]:
        key=(leg["venue"],leg["pool"])
        pool=pool_index.get(key)
        cfg=fee_index.get(key)
        if pool is None or not pool.get("verified") or cfg is None:
            return {"status":"UNQUOTABLE","reason":"missing verified pool or fee","legs_quoted":len(legs),"actionable":False}
        if leg["venue"]!="raydium_cpmm":
            return {"status":"UNQUOTABLE","reason":"unsupported native quote venue","legs_quoted":len(legs),"actionable":False}
        if not cfg.get("fee_verified_onchain"):
            return {"status":"UNQUOTABLE","reason":"fee not verified on chain","legs_quoted":len(legs),"actionable":False}
        fee=cfg["trade_fee_rate_ppm"]+cfg["creator_fee_rate_ppm"]
        try:q=quote_pool(pool,leg["input"],amount,fee)
        except (ValueError,TypeError) as exc:
            return {"status":"UNQUOTABLE","reason":str(exc)[:180],"legs_quoted":len(legs),"actionable":False}
        if q["mint_out"]!=leg["output"]:
            return {"status":"UNQUOTABLE","reason":"route output mint mismatch","legs_quoted":len(legs),"actionable":False}
        amount=q["estimated_output_base_units"]
        legs.append({"venue":leg["venue"],"pool":leg["pool"],"input":q["amount_in"],"estimated_output":amount})
    if not legs or route["legs"][-1]["output"]!=route["start_mint"]:
        return {"status":"UNQUOTABLE","reason":"not a cycle","actionable":False}
    gross=amount-input_amount
    net=None if network_fee is None else gross-network_fee
    return {"status":"INDICATIVE_ONLY","input_base_units":input_amount,
            "estimated_final_base_units":amount,"estimated_gross_base_units":gross,
            "estimated_net_base_units":net,"legs":legs,"legs_quoted":len(legs),
            "actionable":False,"confirmed_profitable":False,
            "reason":"creator fee placement and atomic execution are unverified"}

def scan(rpc,entries,amounts=(100000,1000000)):
    if len(amounts)>8 or any(type(n)is not int or n<=0 for n in amounts):raise ValueError("invalid size budget")
    validation=refresh(rpc,entries)
    if validation["rejected"]:raise ValueError("pool registry validation incomplete")
    pools=validation["verified_pools"]
    graph=cycles(pools,anchors={mint for p in pools for mint in p["mints"]})
    pool_index={(p["venue"],p["address"]):p for p in pools}
    fees={}
    fee_errors=[]
    for p in pools:
        if p["venue"]=="raydium_cpmm":
            try:fees[(p["venue"],p["address"])]=read_pool_config(rpc,p)
            except Exception as exc:fee_errors.append({"pool":p["address"],"error":str(exc)[:180]})
    rankings=[]
    for route in graph:
        for amount in amounts:
            q=score_cycle(route,pool_index,fees,amount)
            rankings.append({"start_mint":route["start_mint"],"hops":route["hops"],
                "venues":route["venues"],"input_base_units":amount,**q})
    rankings.sort(key=lambda q:(q["status"]!="INDICATIVE_ONLY",
                         -(q.get("estimated_gross_base_units") or -10**30)))
    return {"status":"PARTIAL" if fee_errors else "COMPLETE",
        "validated_pools":len(pools),"cycles_discovered":len(graph),
        "screened_size_routes":len(rankings),
        "indicative_routes":sum(x["status"]=="INDICATIVE_ONLY" for x in rankings),
        "unquotable_routes":sum(x["status"]=="UNQUOTABLE" for x in rankings),
        "candidate_rankings":rankings[:100],"fee_errors":fee_errors,
        "actionable_opportunities":0,"confirmed_profitable":0,
        "note":"No actionable ranking until all legs have native verified quotes, execution simulation and net fees."}

def main():
    from arb.arbitrage_mission import check
    check()
    entries=json.load(open("arb/pool_registry.json"))["pools"]
    report=scan(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),entries)
    print(json.dumps(report,indent=2))
    if os.environ.get("CYCLE_SCREEN_REPORT"):
        with open(os.environ["CYCLE_SCREEN_REPORT"],"w") as f:json.dump(report,f,indent=2)
    return 0 if report["status"]=="COMPLETE" else 2
if __name__=="__main__":raise SystemExit(main())
