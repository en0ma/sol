"""Fee-aware *indicative* Raydium CPMM candidate quotes from verified fork state.

Unknown creator-fee placement prevents claiming an executable/native quote.
The configured trade+creator fee is used as a conservative input haircut
for screening only, NOT an authoritative price or guarantee.
"""
import json,os
from arb.pool_registry import refresh
from arb.cpmm_config import read_pool_config
from arb.cpmm_quote import quote_pool,FEE_DENOMINATOR

def screen_pool(rpc,pool,amounts):
    if not pool.get("verified") or pool.get("venue")!="raydium_cpmm":
        raise ValueError("screening requires a verified CPMM pool")
    cfg=read_pool_config(rpc,pool)
    fee=cfg["trade_fee_rate_ppm"]+cfg["creator_fee_rate_ppm"]
    if fee>=FEE_DENOMINATOR:raise ValueError("invalid total fee")
    results=[]
    for mint in pool["mints"]:
        for amount in amounts:
            try:
                q=quote_pool(pool,mint,amount,fee)
                results.append({**q,"conservative_fee_ppm":fee,
                    "config_address":cfg["config_address"],
                    "status":"INDICATIVE_ONLY","actionable":False})
            except ValueError as exc:
                results.append({"mint_in":mint,"amount_in":amount,
                                "status":"REJECTED","reason":str(exc)[:160],
                                "actionable":False})
    return {"pool":pool["address"],"quotes":results,
            "fee_configuration_verified":cfg["fee_verified_onchain"],
            "creator_fee_placement_verified":False,
            "quotes_are_executable":False}

def screen(rpc,entries,amounts=(1000,10000,100000)):
    if len(amounts)>8 or not amounts or any(type(x)is not int or x<=0 for x in amounts):
        raise ValueError("invalid trade-size budget")
    verified=refresh(rpc,[p for p in entries if p.get("venue")=="raydium_cpmm"])
    if verified["rejected"]:raise ValueError("CPMM pool registry revalidation failed")
    reports=[screen_pool(rpc,p,amounts) for p in verified["verified_pools"]]
    return {"status":"SCREENED" if reports else "NO_VERIFIED_POOLS",
            "pools":reports,"indicative_quotes":sum(len(x["quotes"]) for x in reports),
            "actionable_opportunities":0,"atomic_simulations":0,
            "note":"Indicative fee-aware CPMM screening only; no net-profit or swap-executable quote claim."}

def main():
    from arb.arbitrage_mission import check
    check()
    entries=json.load(open("arb/pool_registry.json"))["pools"]
    report=screen(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),entries)
    print(json.dumps(report,indent=2))
    path=os.environ.get("CPMM_QUOTE_REPORT")
    if path:
        with open(path,"w") as f:json.dump(report,f,indent=2)
    return 0 if report["status"]=="SCREENED" else 2

if __name__=="__main__":raise SystemExit(main())
