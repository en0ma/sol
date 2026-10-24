"""Read-only authenticated pool-pair discovery for the next ten atomic routes.

Run against upstream-backed *local* Surfpool before shutting it down.
No account mutation, signer generation, or broadcast; readiness != execution.
"""
import argparse
import base64
import json
from pathlib import Path
from arb.next_ten_atomic_routes import BATCH_10,route_batch
from arb.rpc import call
from arb.pumpswap_local_simulation import local_rpc_only
from arb.orca_whirlpool import PROGRAM as ORCA, decode as orca_decode
from arb.raydium_cpmm import PROGRAM as CPMM, decode as cpmm_decode, verify_vaults
from arb.meteora_damm_v2 import PROGRAM as DAMM, decode as damm_decode, verify as damm_verify
from arb.meteora_dlmm import PROGRAM as DLMM, decode as dlmm_decode, verify as dlmm_verify
from arb.pumpswap_pool import PROGRAM as PUMP, decode as pump_decode, verify as pump_verify
from arb.raydium_clmm import PROGRAM as CLMM, decode as clmm_decode, verify as clmm_verify
from arb.raydium_amm_v4 import decode as amm4_decode
from arb.venue_watchlist import RECOGNIZED_UNSUPPORTED

PROGRAMS={"orca":ORCA,"raydium_cpmm":CPMM,"meteora_damm_v2":DAMM,
          "meteora_dlmm":DLMM,"pumpswap":PUMP,
          "raydium_clmm":CLMM,
          "raydium_amm_v4":next(k for k,v in RECOGNIZED_UNSUPPORTED.items() if v=="raydium_amm_v4")}
DECODERS={"orca":orca_decode,"raydium_cpmm":cpmm_decode,
          "meteora_damm_v2":damm_decode,"meteora_dlmm":dlmm_decode,
          "pumpswap":pump_decode,"raydium_clmm":clmm_decode,
          "raydium_amm_v4":amm4_decode}
MINT_KEYS={"orca":("token_mint_a","token_mint_b"),
           "raydium_cpmm":("token_0_mint","token_1_mint"),
           "meteora_damm_v2":("token_a_mint","token_b_mint"),
           "meteora_dlmm":("token_x_mint","token_y_mint"),
           "pumpswap":("base_mint","quote_mint"),
           "raydium_clmm":("token_mint_0","token_mint_1"),
           "raydium_amm_v4":("base_mint","quote_mint")}
SAFETY={"actionable":False,"live_execution_approved":False,"broadcast":False}

def snapshot(rpc, pool, venue):
    local_rpc_only(rpc)
    if venue not in PROGRAMS:
        raise ValueError("unsupported venue")
    result=call(rpc,"getAccountInfo",[pool,{"encoding":"base64","commitment":"confirmed"}])
    info=result.get("value") if isinstance(result,dict) else None
    if not isinstance(info,dict) or info.get("owner")!=PROGRAMS[venue] or info.get("executable") is not False:
        raise ValueError("missing or wrongly owned "+venue+" pool")
    data=info.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("invalid pool encoding")
    state=DECODERS[venue](base64.b64decode(data[0],validate=True))
    if venue=="raydium_cpmm":
        evidence=verify_vaults(rpc,pool,state,expected_mints=None)
    elif venue=="meteora_damm_v2":
        evidence=damm_verify(rpc,pool,state)
    elif venue=="meteora_dlmm":
        evidence=dlmm_verify(rpc,pool,state)
    elif venue=="pumpswap":
        evidence=pump_verify(rpc,pool,state)
    elif venue=="raydium_clmm":
        evidence=clmm_verify(rpc,pool,state)
    elif venue=="raydium_amm_v4":
        from arb.raydium_amm_v4_preflight import verify_pool_market
        evidence=verify_pool_market(rpc,pool,state)
    else:
        # Orca vaults must be authenticated, not just decode a state hint.
        from arb.token_vaults import TOKEN_PROGRAM, decode_token_account
        addresses=[state["token_vault_a"],state["token_vault_b"]]
        response=call(rpc,"getMultipleAccounts",[
            addresses,{"encoding":"base64","commitment":"confirmed"}])
        vaults=response.get("value") if isinstance(response,dict) else None
        if not isinstance(vaults,list) or len(vaults)!=2:
            raise ValueError("Orca vault snapshot missing")
        for i,vault in enumerate(vaults):
            if not isinstance(vault,dict) or vault.get("owner")!=TOKEN_PROGRAM:
                raise ValueError("Orca vault owner unsupported")
            token=decode_token_account(base64.b64decode(vault["data"][0],validate=True))
            mint=state["token_mint_a" if i==0 else "token_mint_b"]
            if token["mint"]!=mint or token["amount_base_units"]<=0:
                raise ValueError("Orca vault mint or balance mismatch")
        evidence={"slot":response.get("context",{}).get("slot")}
    slot=evidence.get("slot")
    if type(slot) is not int or slot<0:
        raise ValueError("authenticated venue slot missing")
    a,b=(state[key] for key in MINT_KEYS[venue])
    if a==b:
        raise ValueError("duplicate pool mint")
    return {"venue":venue,"pool":pool,"mints":[a,b],
            "slot":slot,"authenticated":True,**SAFETY}

def candidates(registry):
    entries=registry.get("pools")
    if not isinstance(entries,list):
        raise ValueError("missing pool registry")
    result={v:[] for v in PROGRAMS}
    for entry in entries:
        if not isinstance(entry,dict):
            continue
        v=entry.get("venue")
        a=entry.get("address")
        if v in result and isinstance(a,str) and a and a not in result[v]:
            result[v].append(a)
    # Always check the two real working signed pool fixtures.
    from arb.damm_cpmm_atomic_offline import DAMM_POOL, CPMM_POOL
    for venue,pool in (("meteora_damm_v2",DAMM_POOL),("raydium_cpmm",CPMM_POOL)):
        if pool not in result[venue]:
            result[venue].insert(0,pool)
    return result

def probe(rpc, registry, *, batch=BATCH_10):
    local_rpc_only(rpc)
    entries=candidates(registry)
    relevant={v for pair in batch for v in pair}
    pools={}
    failures=[]
    for venue in sorted(relevant):
        pools[venue]=[]
        for pool in entries[venue][:12]:
            try:
                pools[venue].append(snapshot(rpc,pool,venue))
            except (ValueError,KeyError,TypeError) as exc:
                failures.append({"venue":venue,"pool":pool,
                                 "error_class":type(exc).__name__,
                                 "diagnostic":str(exc)[:120]})
    routes=[]
    for first,second in batch:
        combinations=[]
        for a in pools[first]:
            for b in pools[second]:
                if set(a["mints"])==set(b["mints"]):
                    combinations.append({"first_pool":a["pool"],
                                         "second_pool":b["pool"],
                                         "mint_pair":a["mints"],
                                         "first_slot":a["slot"],
                                         "second_slot":b["slot"]})
        routes.append({"first_venue":first,"second_venue":second,
                       "authenticated_pool_pair_candidates":combinations[:10],
                       "candidate_count":len(combinations),
                       "signed_atomic_simulation_verified":False,
                       "rollback_failure_case_verified":False,**SAFETY})
    return {"status":"READONLY_NEXT_TEN_FORK_POOL_AUTHENTICATION",
            "source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
            "route_count":len(routes),"authenticated_pools":pools,
            "route_candidates":routes,"failed_pool_checks":failures,
            "signed_atomic_simulation_verified":False,**SAFETY}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rpc",default="http://127.0.0.1:8899")
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--output",required=True)
    p.add_argument("--batch",choices=("first","next","remaining"),default="first")
    p.add_argument("--only-venue",choices=("raydium_amm_v4",))
    args=p.parse_args()
    report=probe(args.rpc,json.loads(Path(args.registry).read_text()),batch=tuple(pair for pair in route_batch(args.batch) if not args.only_venue or args.only_venue in pair))
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
                      "routes_with_authenticated_candidates":sum(
                        x["candidate_count"]>0 for x in report["route_candidates"]),
                      "signed_atomic_simulation_verified":False,"broadcast":False}))
if __name__=="__main__":
    main()
