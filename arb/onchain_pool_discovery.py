"""Bounded on-chain DEX pool discovery and graph building; no DEX HTTP APIs.

Searches exact curated mint pairs via getProgramAccounts with size/offset
memcmp filters, verifies returned owners and account data, then reads vault
balances before admitting pools to the candidate graph. Read-only.
"""
import argparse,base64,json,os,time
from itertools import combinations
from arb.rpc import call
from arb.orca_whirlpool import PROGRAM as ORCA,SIZE as ORCA_SIZE,decode as decode_orca,SOL,USDC
from arb.raydium_cpmm import PROGRAM as RAY_PROGRAM, SIZE as RAY_SIZE,decode as decode_ray
from arb.raydium_clmm import PROGRAM as CLMM,SIZE as CLMM_SIZE,decode as decode_clmm,verify as verify_clmm
from arb.meteora_dlmm import PROGRAM as DLMM,SIZE as DLMM_SIZE,decode as decode_dlmm,verify as verify_dlmm
from arb.meteora_damm_v2 import PROGRAM as DAMM,SIZE as DAMM_SIZE,decode as decode_damm,verify as verify_damm
from arb.pumpswap_pool import PROGRAM as PUMP_PROGRAM, decode as decode_pump, verify as verify_pump
from arb.raydium_amm_v4 import SIZE as AMM_V4_SIZE, decode as decode_amm_v4
AMM_V4_PROGRAM="675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
from arb.whirlpool_snapshot import snapshot
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account

USDT="Es9vMFrzaCER9UtuaxKVHAn4i98TpxHcv2DgsLg8n4v"
JUP="JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
RAY="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"
MINTS={"WSOL":SOL,"USDC":USDC,"USDT":USDT,"JUP":JUP,"RAY":RAY}
VENUES={"orca":(ORCA,ORCA_SIZE,101,181,decode_orca),
        "raydium_cpmm":(RAY_PROGRAM,RAY_SIZE,168,200,decode_ray),
        "raydium_clmm":(CLMM,CLMM_SIZE,73,105,decode_clmm),
        "meteora_dlmm":(DLMM,DLMM_SIZE,88,120,decode_dlmm),
        "meteora_damm_v2":(DAMM,DAMM_SIZE,168,200,decode_damm),
        "pumpswap":(PUMP_PROGRAM,None,43,75,decode_pump),
        "raydium_amm_v4":(AMM_V4_PROGRAM,AMM_V4_SIZE,400,432,decode_amm_v4)}

def search_pair(rpc,venue,mint_a,mint_b,limit=8,pace_seconds=0):
    if venue not in VENUES or mint_a==mint_b:raise ValueError("invalid search")
    if type(limit)is not int or not 1<=limit<=32:raise ValueError("invalid search limit")
    if type(pace_seconds) not in (int,float) or not 0<=pace_seconds<=5:
        raise ValueError("invalid discovery pacing")
    program,size,offset_a,offset_b,decode=VENUES[venue]
    found={}
    for a,b in ((mint_a,mint_b),(mint_b,mint_a)):
        filters=[{"memcmp":{"offset":offset_a,"bytes":a}},
                 {"memcmp":{"offset":offset_b,"bytes":b}}]
        if size is not None:filters.insert(0,{"dataSize":size})
        config={"encoding":"base64","commitment":"confirmed","filters":filters}
        if pace_seconds:time.sleep(pace_seconds)
        response=call(rpc,"getProgramAccounts",[program,config],timeout=45,
                      retries=4,base_delay=1.0,max_delay=12.0)
        if not isinstance(response,list):
            raise ValueError("unexpected getProgramAccounts result")
        # Fail closed: no silent trimming of incomplete discovery results.
        if len(response)>limit:raise ValueError("pool search exceeded per-order limit")
        for entry in response:
            if entry["account"].get("owner")!=program or entry["account"].get("executable"):
                raise ValueError("wrong program owner")
            raw=base64.b64decode(entry["account"]["data"][0],validate=True)
            decoded=decode(raw)
            mint_fields={"pumpswap":("base_mint","quote_mint"),
                         "meteora_damm_v2":("token_a_mint","token_b_mint"),
                         "meteora_dlmm":("token_x_mint","token_y_mint"),
                         "orca":("token_mint_a","token_mint_b"),
                         "raydium_clmm":("token_mint_0","token_mint_1"),
                         "raydium_cpmm":("token_0_mint","token_1_mint"),
                         "raydium_amm_v4":("base_mint","quote_mint")}
            left,right=mint_fields[venue]
            pair=(decoded[left],decoded[right])
            if pair!=(a,b):raise ValueError("mint filter mismatch")
            found[entry["pubkey"]]=decoded
    return found


def verify_amm_v4(rpc,address,state):
    """Re-read owner-owned legacy pool and two SPL vaults at one context slot.

    OpenOrders liquidity and PnL affect executable pricing; this identity-only
    verifier does NOT imply usable exact pricing, reserves or signed readiness.
    """
    if not isinstance(state,dict) or state.get("status")!=6:
        raise ValueError("AMM v4 swaps not active")
    keys=[address,state["base_vault"],state["quote_vault"],
          state["open_orders"],state["market_id"]]
    response=call(rpc,"getMultipleAccounts",
                  [keys,{"encoding":"base64","commitment":"confirmed"}])
    accounts=response.get("value") if isinstance(response,dict) else None
    slot=response.get("context",{}).get("slot") if isinstance(response,dict) else None
    if not isinstance(accounts,list) or len(accounts)!=5 or type(slot)is not int:
        raise ValueError("AMM v4 source account context incomplete")
    pool=accounts[0]
    if not pool or pool.get("owner")!=AMM_V4_PROGRAM or pool.get("executable") is not False:
        raise ValueError("AMM v4 pool owner invalid")
    raw=base64.b64decode(pool["data"][0],validate=True)
    if decode_amm_v4(raw)!=state:
        raise ValueError("AMM v4 source pool mutated during verification")
    amounts=[]
    for i,mint in enumerate((state["base_mint"],state["quote_mint"])):
        vault=accounts[i+1]
        if not vault or vault.get("owner")!=TOKEN_PROGRAM or vault.get("executable") is not False:
            raise ValueError("AMM v4 SPL vault owner invalid")
        info=decode_token_account(base64.b64decode(vault["data"][0],validate=True))
        if info["mint"]!=mint:
            raise ValueError("AMM v4 vault mint differs from source pool")
        amounts.append(info["amount_base_units"])
    for index in (3,4):
        extra=accounts[index]
        if (not extra or extra.get("owner")!=state["market_program"]
                or extra.get("executable") is not False):
            raise ValueError("AMM v4 OpenOrders/market ownership mismatch")
    if min(amounts)<=0:
        raise ValueError("AMM v4 vault liquidity empty")
    return {"venue":"raydium_amm_v4","address":address,
            "mints":[state["base_mint"],state["quote_mint"]],
            "slot":slot,"vault_base_units":amounts,
            "open_orders_liquidity_reconciled":False,
            "protocol_exact_quote_verified":False,
            "swap_simulated":False}

def verify(rpc,venue,address,state):
    if venue=="raydium_amm_v4":
        return verify_amm_v4(rpc,address,state)
    if venue=="pumpswap":
        p=verify_pump(rpc,address,state)
        return {**p,"mints":[p["base_mint"],p["quote_mint"]],
                "vault_base_units":[p["base_reserve"],p["quote_vault_balance"]],
                "swap_simulated":False}
    if venue=="meteora_damm_v2":
        return verify_damm(rpc,address,state)
    if venue=="meteora_dlmm":
        return verify_dlmm(rpc,address,state)
    if venue=="raydium_clmm":
        return verify_clmm(rpc,address,state)
    if venue=="orca":
        s=snapshot(rpc,address)
        if s["pool"]!=state:raise ValueError("Orca account changed while validating")
        amounts=[s["vault_a"]["amount_base_units"],s["vault_b"]["amount_base_units"]]
        pair=(state["token_mint_a"],state["token_mint_b"])
        slot=s["slot"]
    else:
        if not state["swap_enabled"]:raise ValueError("Raydium swaps disabled")
        if state["token_0_program"]!=TOKEN_PROGRAM or state["token_1_program"]!=TOKEN_PROGRAM:
            raise ValueError("unsupported token program")
        keys=[address,state["token_0_vault"],state["token_1_vault"]]
        resp=call(rpc,"getMultipleAccounts",[keys,{"encoding":"base64","commitment":"confirmed"}])
        values=resp.get("value")
        if not isinstance(values,list) or len(values)!=3:raise ValueError("missing Raydium accounts")
        pool=values[0]
        if not pool or pool.get("owner")!=RAY_PROGRAM or decode_ray(base64.b64decode(pool["data"][0],validate=True))!=state:
            raise ValueError("Raydium state mutated")
        amounts=[]
        for i in (0,1):
            vault=values[i+1]
            if not vault or vault.get("owner")!=TOKEN_PROGRAM:raise ValueError("invalid vault owner")
            decoded=decode_token_account(base64.b64decode(vault["data"][0],validate=True))
            if decoded["mint"]!=state[f"token_{i}_mint"]:raise ValueError("vault mint mismatch")
            amounts.append(decoded["amount_base_units"])
        pair=(state["token_0_mint"],state["token_1_mint"])
        slot=resp.get("context",{}).get("slot")
    if min(amounts)<=0:raise ValueError("empty reserves")
    return {"venue":venue,"address":address,"mints":list(pair),"slot":slot,
            "vault_base_units":amounts,"swap_simulated":False}

def discover(rpc,pairs,limit=8,pace_seconds=0,registry_entries=None,venues=None):
    order=list(VENUES) if venues is None else list(venues)
    if len(order)!=len(set(order)) or not order or any(v not in VENUES for v in order):
        raise ValueError("invalid venue discovery selection")
    results=[];errors=[]
    upstream_rate_limited=False
    venue_attempts={venue:{"attempted_pairs":0,"verified_pools":0,
                            "errors":0,"status":"NOT_ATTEMPTED"} for venue in VENUES}
    for a,b in pairs:
        for venue in order:
            if upstream_rate_limited:break
            stats=venue_attempts[venue]
            stats["attempted_pairs"]+=1
            stats["status"]="SEARCHED"
            try:
                found=search_pair(rpc,venue,a,b,limit,pace_seconds=pace_seconds)
                for address,state in found.items():
                    try:
                        result=verify(rpc,venue,address,state)
                        results.append(result)
                        stats["verified_pools"]+=1
                    except ValueError as exc:
                        stats["errors"]+=1
                        errors.append({"venue":venue,"address":address,"error":str(exc)})
            except Exception as exc:
                message=type(exc).__name__+": "+str(exc)[:250]
                stats["errors"]+=1
                errors.append({"venue":venue,"pair":[a,b],"error":message})
                if "429" in message or "too many requests" in message.lower():
                    upstream_rate_limited=True
                    stats["status"]="RATE_LIMITED"
    for venue,stats in venue_attempts.items():
        if venue not in order:
            stats["status"]="NOT_SELECTED"
        elif stats["status"]=="NOT_ATTEMPTED" and upstream_rate_limited:
            stats["status"]="SKIPPED_UPSTREAM_RATE_LIMIT"
    fallback = None
    if upstream_rate_limited and registry_entries is not None:
        # Direct address reads avoid globally rate-limited getProgramAccounts.
        # Independently validate identity and vaults; do not call these newly found.
        from arb.pool_registry import refresh
        fallback = refresh(rpc,registry_entries)
    # Candidate graph can use revalidated identities without conflating them
    # with newly discovered pools. Duplicate identities are counted once.
    combined={(p["venue"],p["address"]):p for p in results}
    if fallback:
        for p in fallback["verified_pools"]:
            combined.setdefault((p["venue"],p["address"]),p)
    by_pair={}
    for pool in combined.values():
        key=tuple(sorted(pool["mints"]))
        by_pair.setdefault(key,set()).add(pool["venue"])
    shared=[{"mints":list(k),"venues":sorted(v)} for k,v in by_pair.items() if len(v)>1]
    return {"status":("UPSTREAM_RATE_LIMITED" if upstream_rate_limited else
                      "COMPLETE" if not errors else "PARTIAL"),
            "pools_verified":len(results),
            "venue_attempts":venue_attempts,
            "candidate_graph_verified_count":len(combined),
            "candidate_graph_pool_identities":[{"venue":p["venue"],"address":p["address"],
                "mints":p["mints"],"slot":p["slot"],"swap_simulated":False}
                for p in combined.values()],
            "shared_pairs":shared,
            "pools":results,"errors":errors,
            "direct_registry_fallback":fallback,
            "route_simulated":False,"profitable_opportunities_confirmed":0}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pairs",default="WSOL/USDT,WSOL/JUP,USDC/USDT")
    p.add_argument("--output",default=os.environ.get("DEX_DISCOVERY_REPORT",""))
    p.add_argument("--limit",type=int,default=8)
    p.add_argument("--pace-seconds",type=float,default=0)
    p.add_argument("--registry-fallback",default="")
    p.add_argument("--venues",default=",".join(VENUES))
    args=p.parse_args()
    pairs=[]
    for item in args.pairs.split(","):
        a,b=item.strip().split("/")
        if a not in MINTS or b not in MINTS:raise ValueError("mint not on curated allowlist")
        pairs.append((MINTS[a],MINTS[b]))
    if len(pairs)>6:raise ValueError("pair budget exceeded")
    entries=(json.load(open(args.registry_fallback))["pools"]
             if args.registry_fallback else None)
    report=discover(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),pairs,args.limit,
                    pace_seconds=args.pace_seconds,registry_entries=entries,
                    venues=[v.strip() for v in args.venues.split(",")])
    print(json.dumps(report,indent=2))
    if args.output:
        with open(args.output,"w") as f:json.dump(report,f,indent=2)
    # No pools is a legitimate observation; incomplete RPC reads are not.
    return 0 if report["status"]=="COMPLETE" else 2
if __name__=="__main__":raise SystemExit(main())
