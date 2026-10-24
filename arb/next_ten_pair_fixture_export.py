"""Export authenticated paired account + executable fixture from read-only Surfpool.

This is a *fixture*, never signed execution. Hydration is performed only by a
separate --offline process and only after independent program-data validation.
"""
import argparse
import base64
import json
from pathlib import Path
from solders.pubkey import Pubkey
from arb.rpc import call
from arb.pumpswap_local_simulation import local_rpc_only
from arb.next_ten_fork_pool_probe import PROGRAMS, snapshot
from arb.next_ten_atomic_routes import BATCH_10
from arb.damm_cpmm_atomic_offline import _fetch, LOADER

def program_data_accounts(rpc, programs):
    found={}
    for program in sorted(programs):
        account=_fetch(rpc,[program])[program]
        raw=base64.b64decode(account["data"][0],validate=True)
        if (account["owner"]!=LOADER or account.get("executable") is not True
                or raw[:4]!=bytes([2,0,0,0]) or len(raw)<36):
            raise ValueError("invalid authenticated upgradeable executable")
        pd_address=str(Pubkey.from_bytes(raw[4:36]))
        pd=_fetch(rpc,[pd_address])[pd_address]
        raw_pd=base64.b64decode(pd["data"][0],validate=True)
        if (pd["owner"]!=LOADER or raw_pd[:4]!=bytes([3,0,0,0])
                or raw_pd[45:49]!=bytes([127,69,76,70])):
            raise ValueError("missing authenticated venue ELF")
        found[program]=account
        found[pd_address]=pd
    return found

def venue_accounts(rpc, venue, pool, mints):
    from arb.next_ten_fork_pool_probe import snapshot, MINT_KEYS
    from arb.orca_whirlpool import fetch_pool as fetch_orca
    from arb.whirlpool_swap import select_tick_arrays
    from arb.whirlpool_preflight import verify_oracle
    from arb.meteora_damm_v2 import decode as decode_damm
    from arb.raydium_cpmm import decode as decode_cpmm
    from arb.meteora_dlmm import decode as decode_dlmm
    from arb.meteora_dlmm_bin_preflight import check_active_bin_array
    from arb.pumpswap_pool import decode as decode_pump
    authenticated=snapshot(rpc,pool,venue)
    if set(authenticated["mints"])!=set(mints):
        raise ValueError("pool mint identity changed after route selection")
    data=_fetch(rpc,[pool])[pool]["data"][0]
    raw=base64.b64decode(data,validate=True)
    extras=[pool,*mints]
    evidence={}
    if venue=="orca":
        state=fetch_orca(rpc,pool)
        oracle=verify_oracle(rpc,pool,adaptive_fee=state["tick_spacing"]!=state["fee_tier_index_seed"])
        arrays=set()
        for forward in (True,False):
            arrays.update(select_tick_arrays(pool,state["tick_current_index"],state["tick_spacing"],forward))
        extras += [state["token_vault_a"],state["token_vault_b"],*sorted(arrays)]
        # Non-adaptive Whirlpool oracles may not exist on chain.
        # getAccountInfo permits a null optional oracle; strict _fetch does not.
        optional=call(rpc,"getAccountInfo",[oracle,{"encoding":"base64"}])["value"]
        if optional is not None:
            extras.append(oracle)
        evidence={"oracle":oracle,"tick_arrays":sorted(arrays)}
    elif venue=="meteora_damm_v2":
        state=decode_damm(raw)
        extras += [state["token_a_vault"],state["token_b_vault"]]
    elif venue=="raydium_cpmm":
        state=decode_cpmm(raw)
        extras += [state["token_0_vault"],state["token_1_vault"],
                   state["amm_config"],state["observation"]]
    elif venue=="meteora_dlmm":
        state=decode_dlmm(raw)
        preflight=check_active_bin_array(rpc,pool)
        if preflight.get("status")!="ACTIVE_BIN_ARRAY_AUTHENTICATED":
            raise ValueError("DLMM bins not authenticated")
        bins=[v["pda"] for v in preflight["neighboring_bin_arrays"]
              if v.get("authenticated")]
        extras += [state["reserve_x"],state["reserve_y"],state["oracle"],*bins]
        evidence={"bin_preflight":preflight,"bin_arrays":bins,
                  "active_bin_array_index":preflight["active_bin_array_index"]}
    elif venue=="pumpswap":
        from arb.pumpswap_global_config import ADDRESS as CONFIG
        from arb.pumpswap_fee_account import authenticated_address
        state=decode_pump(raw)
        extras += [state["base_vault"],state["quote_vault"],CONFIG,authenticated_address()[0]]
    else:
        raise ValueError("unsupported fixture venue")
    return list(dict.fromkeys(extras)),evidence

def export(rpc,readiness,route_index,output):
    local_rpc_only(rpc)
    if type(route_index) is not int or not 0<=route_index<len(BATCH_10):
        raise ValueError("route index outside first ten")
    if readiness.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL":
        raise ValueError("not an authenticated source-fork report")
    route=BATCH_10[route_index]
    rows=readiness.get("route_candidates")
    if not isinstance(rows,list) or len(rows)!=10:
        raise ValueError("read-only source route candidates missing")
    target=rows[route_index]
    if (target.get("first_venue"),target.get("second_venue"))!=route:
        raise ValueError("candidate direction mismatch")
    choices=target.get("authenticated_pool_pair_candidates")
    if not isinstance(choices,list) or not choices:
        raise ValueError("no authenticated compatible source-fork pools for route")
    choice=choices[0]
    first,second=route
    addresses=[]
    leg_evidence={}
    mints=choice["mint_pair"]
    for venue,pool in ((first,choice["first_pool"]),(second,choice["second_pool"])):
        extras,proof=venue_accounts(rpc,venue,pool,mints)
        addresses.extend(extras)
        leg_evidence[venue]={"pool":pool,**proof}
    addresses=list(dict.fromkeys(addresses))
    if len(addresses)>64:
        raise ValueError("overlarge paired fixture account inventory")
    accounts=_fetch(rpc,addresses)
    if any(v is None for v in accounts.values()):
        raise ValueError("required authenticated account unavailable")
    accounts.update(program_data_accounts(rpc,(PROGRAMS[first],PROGRAMS[second])))
    output_data={"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
                 "first_venue":first,"second_venue":second,
                 "route_mints":[mints[0],mints[1],mints[0]],
                 "first_pool":choice["first_pool"],"second_pool":choice["second_pool"],
                 "leg_evidence":leg_evidence,"accounts":accounts,
                 "signed_atomic_simulation_verified":False,
                 "actionable":False,"live_execution_approved":False,"broadcast":False}
    Path(output).write_text(json.dumps(output_data))
    return {"status":"AUTHENTICATED_DUAL_PROGRAM_SOURCE_FIXTURE",
            "first_venue":first,"second_venue":second,
            "account_count":len(accounts),"broadcast":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rpc",default="http://127.0.0.1:8899")
    p.add_argument("--readiness",required=True)
    p.add_argument("--output-dir",required=True)
    args=p.parse_args()
    root=Path(args.output_dir)
    root.mkdir(parents=True,exist_ok=True)
    ready=json.loads(Path(args.readiness).read_text())
    reports=[]
    for index,(first,second) in enumerate(BATCH_10):
        try:
            reports.append(export(args.rpc,ready,index,
                                  root/(first+"__"+second+".json")))
        except (ValueError,KeyError,TypeError) as exc:
            reports.append({"status":"SOURCE_FIXTURE_BLOCKED","first_venue":first,
                            "second_venue":second,"reason":str(exc)[:200],
                            "broadcast":False})
    summary={"status":"READ_ONLY_PAIRED_FIXTURE_EXPORT",
             "routes":reports,"exported":sum(x["status"]=="AUTHENTICATED_DUAL_PROGRAM_SOURCE_FIXTURE" for x in reports),
             "actionable":False,"live_execution_approved":False,"broadcast":False}
    (root/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps({"exported":summary["exported"],"target":10,"broadcast":False}))
if __name__=="__main__":
    main()
