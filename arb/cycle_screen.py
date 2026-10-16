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

def score_cycle(route,pool_index,fee_index,input_amount,network_fee=None,max_slot_spread=None,orca_evidence=None,clmm_quote=None):
    if type(input_amount)is not int or input_amount<=0:raise ValueError("invalid input size")
    if network_fee is not None and (type(network_fee)is not int or network_fee<0):
        raise ValueError("invalid network fee")
    if max_slot_spread is not None and (type(max_slot_spread) is not int or max_slot_spread<0):
        raise ValueError("invalid slot spread budget")
    # Never price malformed walks as arbitrage, even if their individual pools quote.
    path=route.get("legs")
    start=route.get("start_mint")
    if not isinstance(path,list) or not 2<=len(path)<=4 or not isinstance(start,str) or not start:
        # Diagnostic callers may probe a single unsupported leg. Preserve its
        # venue attribution without ever treating it as a priced cycle.
        venue=(path[0].get("venue") if isinstance(path,list) and path and isinstance(path[0],dict) else None)
        result={"status":"UNQUOTABLE","reason":"invalid cycle topology","legs_quoted":0,"actionable":False}
        if isinstance(venue,str) and venue:
            result["missing_quote_venue"]=venue
        return result
    current=start
    seen=set()
    for leg in path:
        if not isinstance(leg,dict) or leg.get("input")!=current or not isinstance(leg.get("output"),str) or not leg["output"]:
            return {"status":"UNQUOTABLE","reason":"disconnected cycle topology","legs_quoted":0,"actionable":False}
        key=(leg.get("venue"),leg.get("pool"))
        if any(not isinstance(v,str) or not v for v in key) or key in seen:
            return {"status":"UNQUOTABLE","reason":"invalid or reused cycle pool","legs_quoted":0,"actionable":False}
        seen.add(key)
        current=leg["output"]
    if current!=start:
        return {"status":"UNQUOTABLE","reason":"cycle does not return to start","legs_quoted":0,"actionable":False}
    if max_slot_spread is not None:
        slots=[]
        for leg in path:
            pool=pool_index.get((leg["venue"],leg["pool"]))
            slot=pool.get("slot") if isinstance(pool,dict) else None
            if type(slot) is not int or slot<0:
                return {"status":"UNQUOTABLE","reason":"missing verified pool slot",
                        "legs_quoted":0,"actionable":False}
            slots.append(slot)
        if max(slots)-min(slots)>max_slot_spread:
            return {"status":"UNQUOTABLE","reason":"stale cross-pool slot spread",
                    "slot_spread":max(slots)-min(slots),
                    "legs_quoted":0,"actionable":False}
    amount=input_amount
    legs=[]
    for leg in route["legs"]:
        key=(leg["venue"],leg["pool"])
        pool=pool_index.get(key)
        cfg=fee_index.get(key)
        if pool is None or not pool.get("verified"):
            return {"status":"UNQUOTABLE","reason":"missing verified pool","missing_quote_venue":leg["venue"],"legs_quoted":len(legs),"actionable":False}
        if leg["venue"]=="orca":
            proof=(orca_evidence or {}).get(key)
            if not isinstance(proof,dict) or proof.get("verified") is not True:
                return {"status":"UNQUOTABLE","reason":"missing validated Orca tick arrays",
                        "missing_quote_venue":"orca","legs_quoted":len(legs),"actionable":False}
            try:
                from arb.orca_multitick_quote import quote_from_decoded_arrays
                q=quote_from_decoded_arrays(proof["state"],leg["input"],amount,proof["arrays"])
                if q["mint_out"]!=leg["output"]:
                    raise ValueError("Orca output mint mismatch")
                amount=q["estimated_output_base_units"]
                legs.append({"venue":"orca","pool":leg["pool"],"input":q["amount_in"],
                             "estimated_output":amount,"ticks_crossed":q["ticks_crossed"]})
                continue
            except (KeyError,ValueError,TypeError) as exc:
                return {"status":"UNQUOTABLE","reason":str(exc)[:180],
                        "missing_quote_venue":"orca","legs_quoted":len(legs),"actionable":False}
        if leg["venue"]=="raydium_clmm":
            if clmm_quote is None:
                return {"status":"UNQUOTABLE","reason":"missing authenticated CLMM quote adapter",
                        "missing_quote_venue":"raydium_clmm","legs_quoted":len(legs),"actionable":False}
            try:
                q=clmm_quote(leg["pool"],leg["input"],amount)
                if (q.get("status")!="INDICATIVE_WITHIN_TICK_ONLY" or
                    q.get("mint_out")!=leg["output"] or
                    q.get("actionable") is not False or
                    q.get("executable_quote") is not False or
                    type(q.get("estimated_output_base_units")) is not int or
                    q["estimated_output_base_units"]<=0):
                    raise ValueError("invalid indicative CLMM quote provenance")
                # Validate the quote's actual snapshot against the registry
                # snapshot used for every other leg. Refuse silently mixed slots.
                if q.get("pool")!=leg["pool"] or type(q.get("slot")) is not int:
                    raise ValueError("CLMM quote missing authenticated pool/slot provenance")
                if abs(q["slot"]-pool["slot"])>8:
                    raise ValueError("CLMM quote stale relative to verified route pool")
                amount=q["estimated_output_base_units"]
                legs.append({"venue":"raydium_clmm","pool":leg["pool"],
                             "input":q["amount_in"],"estimated_output":amount,
                             "crossed_ticks":0})
                continue
            except (KeyError,ValueError,TypeError) as exc:
                return {"status":"UNQUOTABLE","reason":str(exc)[:180],
                        "missing_quote_venue":"raydium_clmm","legs_quoted":len(legs),"actionable":False}
        if leg["venue"]!="raydium_cpmm":
            return {"status":"UNQUOTABLE","reason":"unsupported native quote venue","missing_quote_venue":leg["venue"],"legs_quoted":len(legs),"actionable":False}
        if cfg is None:
            return {"status":"UNQUOTABLE","reason":"missing verified fee configuration","missing_quote_venue":leg["venue"],"legs_quoted":len(legs),"actionable":False}
        if not cfg.get("fee_verified_onchain"):
            return {"status":"UNQUOTABLE","reason":"fee not verified on chain","legs_quoted":len(legs),"actionable":False}
        try:
            trade_fee=cfg["trade_fee_rate_ppm"]
            creator_fee=cfg["creator_fee_rate_ppm"]
            if type(trade_fee) is not int or type(creator_fee) is not int:
                raise ValueError("invalid fee type")
            fee=trade_fee+creator_fee
            q=quote_pool(pool,leg["input"],amount,fee)
        except (ValueError,TypeError,KeyError) as exc:
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

def scan(rpc,entries,amounts=(100000,1000000),max_slot_spread=8,extra_entries=()):
    if len(amounts)>8 or any(type(n)is not int or n<=0 for n in amounts):raise ValueError("invalid size budget")
    if type(max_slot_spread) is not int or not 0<=max_slot_spread<=1000:
        raise ValueError("invalid scan slot spread budget")
    # Additional addresses are hints, never trusted snapshots. Revalidate all
    # pool state, ownership and reserves before constructing cycle edges.
    identities=set()
    merged=[]
    for item in list(entries)+list(extra_entries):
        if not isinstance(item,dict):raise ValueError("invalid pool identity hint")
        key=(item.get("venue"),item.get("address"))
        if key not in identities:
            identities.add(key)
            merged.append(item)
    if len(merged)>200:raise ValueError("pool registry budget exceeded")
    validation=refresh(rpc,merged)
    if validation["rejected"]:raise ValueError("pool registry validation incomplete")
    pools=validation["verified_pools"]
    graph=(cycles(pools,anchors={mint for p in pools for mint in p["mints"]})
           if pools else [])
    pool_index={(p["venue"],p["address"]):p for p in pools}
    fees={}
    fee_errors=[]
    orca_evidence={}
    from arb.whirlpool_ticks import inspect as inspect_orca
    for p in pools:
        if p["venue"]!="orca":continue
        try:
            observation=inspect_orca(rpc,p["address"])
            state=observation["pool_state"]
            tick_slot=observation.get("slot")
            pool_slot=p.get("slot")
            if (type(tick_slot) is not int or type(pool_slot) is not int or
                    abs(tick_slot-pool_slot)>max_slot_spread or
                    sorted((state["token_mint_a"],state["token_mint_b"]))!=sorted(p["mints"])):
                raise ValueError("Orca tick snapshot not aligned with verified pool slot")
            orca_evidence[(p["venue"],p["address"])]={"verified":True,
                "state":state,"arrays":observation["arrays"]}
        except Exception as exc:
            fee_errors.append({"pool":p["address"],"venue":"orca",
                               "error":str(exc)[:180]})
    for p in pools:
        if p["venue"]=="raydium_cpmm":
            try:fees[(p["venue"],p["address"])]=read_pool_config(rpc,p)
            except Exception as exc:fee_errors.append({"pool":p["address"],"error":str(exc)[:180]})
    # Count every missing leg, not merely the first blocked leg of each cycle.
    # This identifies where implementing one quote adapter unlocks most routes.
    missing_by_venue={}
    for route in graph:
        for leg in route["legs"]:
            key=(leg["venue"],leg["pool"])
            if leg["venue"]!="raydium_cpmm" or key not in fees:
                entry=missing_by_venue.setdefault(leg["venue"],{"blocked_route_legs":0,"unique_pools":set()})
                entry["blocked_route_legs"]+=1
                entry["unique_pools"].add(leg["pool"])
    # Count distinct routes unlocked by one adapter, versus raw leg frequency.
    # A route needing multiple missing venues is not unlocked by only one.
    sole_missing_routes={}
    for route in graph:
        missing={leg["venue"] for leg in route["legs"]
                 if leg["venue"]!="raydium_cpmm" or
                    (leg["venue"],leg["pool"]) not in fees}
        if len(missing)==1:
            venue=next(iter(missing))
            sole_missing_routes[venue]=sole_missing_routes.get(venue,0)+1
    quote_gap_priorities=sorted((
        {"venue":venue,"blocked_route_legs":x["blocked_route_legs"],
         "unique_pools":len(x["unique_pools"]),
         "routes_unlocked_by_single_adapter":sole_missing_routes.get(venue,0)}
        for venue,x in missing_by_venue.items()),
        key=lambda x:(-x["routes_unlocked_by_single_adapter"],
                      -x["blocked_route_legs"],-x["unique_pools"],x["venue"]))
    from arb.raydium_clmm_live_quote import quote_live
    def clmm_quote(address,mint,amount):
        return quote_live(rpc,address,mint,amount)
    rankings=[]
    for route in graph:
        for amount in amounts:
            q=score_cycle(route,pool_index,fees,amount,max_slot_spread=max_slot_spread,
                          orca_evidence=orca_evidence,clmm_quote=clmm_quote)
            rankings.append({"start_mint":route["start_mint"],"hops":route["hops"],
                "route_legs":[dict(leg) for leg in route["legs"]],
                "venues":route["venues"],"input_base_units":amount,**q})
    # Quote blockers reflect actual attempted sizes, not static venue labels.
    # A verified Orca tick snapshot can quote a leg in one route direction and
    # fail in another; raw unsupported-venue totals overstate the remaining gap.
    actual_blockers={}
    for result in rankings:
        venue=result.get("missing_quote_venue")
        if result.get("status")!="UNQUOTABLE" or not isinstance(venue,str):
            continue
        entry=actual_blockers.setdefault(venue,{"unquotable_size_routes":0,
            "reasons":{}})
        entry["unquotable_size_routes"]+=1
        reason=result.get("reason","unknown")
        entry["reasons"][reason]=entry["reasons"].get(reason,0)+1
    # Preserve executable route identity for downstream simulation candidates.
    # Sort only comparable base units: never rank one starting mint against
    # another as if their raw integer denominations were interchangeable.
    rankings.sort(key=lambda q:(q["status"]!="INDICATIVE_ONLY",
                         q["start_mint"],
                         -q.get("estimated_gross_base_units", -(10**30)),
                         q["input_base_units"]))
    return {"status":"PARTIAL" if fee_errors else "COMPLETE",
        "validated_pools":len(pools),"cycles_discovered":len(graph),
        "screened_size_routes":len(rankings),
        "indicative_routes":sum(x["status"]=="INDICATIVE_ONLY" for x in rankings),
        "stale_slot_routes":sum(x.get("reason")=="stale cross-pool slot spread" for x in rankings),
        "missing_slot_routes":sum(x.get("reason")=="missing verified pool slot" for x in rankings),
        "max_pool_slot_spread":max_slot_spread,
        "unquotable_routes":sum(x["status"]=="UNQUOTABLE" for x in rankings),
        "candidate_rankings":rankings[:100],
        "indicative_positive_gross_count":sum(x["status"]=="INDICATIVE_ONLY" and x.get("estimated_gross_base_units",0)>0 for x in rankings),
        "orca_tick_snapshots":len(orca_evidence),
        "actual_quote_blockers":actual_blockers,
        "quote_gap_priorities":quote_gap_priorities,"fee_errors":fee_errors,
        "actionable_opportunities":0,"confirmed_profitable":0,
        "note":"No actionable ranking until all legs have native verified quotes, execution simulation and net fees."}

def main():
    from arb.arbitrage_mission import check
    check()
    entries=json.load(open("arb/pool_registry.json"))["pools"]
    extra=[]
    discovery=os.environ.get("DEX_DISCOVERY_INPUT")
    if discovery and os.path.isfile(discovery):
        report_data=json.load(open(discovery))
        hints=report_data.get("candidate_graph_pool_identities",[])
        if not isinstance(hints,list) or len(hints)>200:
            raise ValueError("invalid discovery candidate list")
        extra=[{"venue":h["venue"],"address":h["address"],"mints":h["mints"]}
               for h in hints]
    report=scan(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),entries,
                extra_entries=extra)
    print(json.dumps(report,indent=2))
    if os.environ.get("CYCLE_SCREEN_REPORT"):
        with open(os.environ["CYCLE_SCREEN_REPORT"],"w") as f:json.dump(report,f,indent=2)
    return 0 if report["status"]=="COMPLETE" else 2
if __name__=="__main__":raise SystemExit(main())
