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
from arb.next_ten_atomic_routes import BATCH_10,route_batch
from arb.damm_cpmm_atomic_offline import _fetch, LOADER
from arb.source_snapshot_manifest import digest

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
    elif venue=="raydium_clmm":
        from arb.raydium_clmm_ticks import inspect
        state=__import__("arb.raydium_clmm",fromlist=["decode"]).decode(raw)
        extras += [state["token_vault_0"],state["token_vault_1"],
                   state["amm_config"],state["observation_key"]]
        directions={}
        for zero_for_one in (True,False):
            result=inspect(rpc,pool,zero_for_one=zero_for_one)
            if result["all_arrays_valid"]:
                directions["0_to_1" if zero_for_one else "1_to_0"]=[
                    item["address"] for item in result["tick_arrays"]]
                extras.extend(directions["0_to_1" if zero_for_one else "1_to_0"])
        if not directions:
            raise ValueError("no authenticated CLMM tick array direction")
        evidence={"tick_arrays_by_direction":directions}
    elif venue=="raydium_amm_v4":
        from arb.raydium_amm_v4_preflight import verify_pool_market
        from arb.raydium_amm_v4 import decode
        state=decode(raw)
        preflight=verify_pool_market(rpc,pool,state)
        extras += [state["base_vault"],state["quote_vault"],
                   state["open_orders"],state["market_id"],
                   state["target_orders"]]
        from arb.raydium_amm_v4_preflight import authenticate_swap_market
        roles=authenticate_swap_market(rpc,pool,state)
        extras.extend(roles["market_role_addresses"])
        evidence={"market_preflight":preflight,**roles}
    elif venue=="pumpswap":
        from arb.pumpswap_global_config import ADDRESS as CONFIG
        from arb.pumpswap_fee_account import authenticated_address
        state=decode_pump(raw)
        # Fetch authenticated pool + fee configuration and derive stable
        # protocol/creator destinations with the existing PumpSwap resolver.
        from arb.pumpswap_pool import verify as verify_pump
        from arb.pumpswap_account_resolver import resolve
        from solders.keypair import Keypair
        verified=verify_pump(rpc,pool,state)
        recipient=verified["global_config"]["protocol_fee_recipients"][0]
        # Ephemeral user keys are substituted at offline signing time.
        placeholder=str(Keypair().pubkey())
        derived=resolve(verified,placeholder,placeholder,placeholder,recipient)
        extras += [state["base_vault"],state["quote_vault"],CONFIG,
                   authenticated_address()[0]]
        # Many fee/creator/volume accounts are optional during execution.
        # Capture existent source accounts, never fabricate source data.
        optional_keys=("protocol_fee_recipient_token_account",
                       "coin_creator_vault_ata","global_volume_accumulator")
        optional={}
        for key in optional_keys:
            address=derived[key]
            info=call(rpc,"getAccountInfo",[address,{"encoding":"base64"}])["value"]
            if info is not None:
                extras.append(address)
                optional[key]=address
        # V2 trades require an authenticated buyback recipient quote ATA
        # sourced from the current GlobalConfig buyback wallet table.
        from arb.pumpswap_global_config import authenticated_buyback_wallets
        from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
        from arb.pumpswap_account_resolver import ATA
        from solders.pubkey import Pubkey
        config_raw=base64.b64decode(_fetch(rpc,[CONFIG])[CONFIG]["data"][0],validate=True)
        wallets=authenticated_buyback_wallets(config_raw)
        buyback_ata=None
        for wallet in wallets:
            candidate=str(Pubkey.find_program_address(
                [bytes(Pubkey.from_string(wallet)),bytes(Pubkey.from_string(TOKEN_PROGRAM)),
                 bytes(Pubkey.from_string(state["quote_mint"]))],Pubkey.from_string(ATA))[0])
            info=call(rpc,"getAccountInfo",[candidate,{"encoding":"base64"}])["value"]
            if not info or info.get("owner")!=TOKEN_PROGRAM:
                continue
            token=decode_token_account(base64.b64decode(info["data"][0],validate=True))
            if token["mint"]==state["quote_mint"] and token["authority"]==wallet:
                buyback_ata=candidate
                extras.append(candidate)
                break
        if not buyback_ata:
            raise ValueError("authenticated PumpSwap V2 buyback recipient ATA missing")
        evidence={"verified_pool":verified,
                  "buyback_fee_recipient":buyback_ata,
                  "protocol_fee_recipient":recipient,
                  "derived_source_accounts":optional}
    else:
        raise ValueError("unsupported fixture venue")
    return list(dict.fromkeys(extras)),evidence

def export(rpc,readiness,route_index,output,*,batch=BATCH_10):
    local_rpc_only(rpc)
    if type(route_index) is not int or not 0<=route_index<len(batch):
        raise ValueError("route index outside first ten")
    if readiness.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL":
        raise ValueError("not an authenticated source-fork report")
    route=batch[route_index]
    rows=readiness.get("route_candidates")
    if not isinstance(rows,list) or len(rows)!=len(batch):
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
    # PumpSwap uses the separately deployed pump_fees program as an
    # executable account. Copy its authenticated ELF as well, not merely
    # the PumpSwap AMM executable.
    executable_programs={PROGRAMS[first],PROGRAMS[second]}
    if "pumpswap" in (first,second):
        from arb.pumpswap_fee_account import PROGRAM as FEE_PROGRAM
        executable_programs.add(FEE_PROGRAM)
    accounts.update(program_data_accounts(rpc,executable_programs))
    # One contextual RPC response covers the entire selected non-program
    # state inventory, not just the two pool accounts. Verify byte-for-byte
    # agreement with the independently preflighted accounts before retaining
    # any timestamp. Programs and upgradeable ELF were fetched separately.
    contextual=call(rpc,"getMultipleAccounts",[
        addresses,{"encoding":"base64","commitment":"confirmed"}])
    state_slot=contextual.get("context",{}).get("slot")
    state_values=contextual.get("value")
    if (type(state_slot)is not int or state_slot<0 or
        not isinstance(state_values,list) or len(state_values)!=len(addresses)):
        raise ValueError("missing contextual companion-account snapshot")
    for address,value in zip(addresses,state_values):
        if not isinstance(value,dict) or value!=accounts[address]:
            raise ValueError("contextual companion accounts differ from authenticated inventory")
    paired_slot=state_slot
    output_data={"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
                 "first_venue":first,"second_venue":second,
                 "paired_pool_observed_slot":paired_slot,
                 "state_accounts_observed_slot":state_slot,
                 "state_account_count":len(addresses),
                 "state_account_addresses":addresses,
                 "state_account_manifest_sha256":digest(accounts,addresses,state_slot),
                 "full_source_snapshot_slot":None,
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
    p.add_argument("--batch",choices=("first","next","remaining"),default="first")
    p.add_argument("--only-venue",choices=("raydium_amm_v4",))
    args=p.parse_args()
    root=Path(args.output_dir)
    root.mkdir(parents=True,exist_ok=True)
    ready=json.loads(Path(args.readiness).read_text())
    reports=[]
    selected=tuple(pair for pair in route_batch(args.batch) if not args.only_venue or args.only_venue in pair)
    for index,(first,second) in enumerate(selected):
        try:
            reports.append(export(args.rpc,ready,index,
                                  root/(first+"__"+second+".json"),batch=selected))
        except (ValueError,KeyError,TypeError) as exc:
            reports.append({"status":"SOURCE_FIXTURE_BLOCKED","first_venue":first,
                            "second_venue":second,"reason":str(exc)[:200],
                            "broadcast":False})
    summary={"status":"READ_ONLY_PAIRED_FIXTURE_EXPORT",
             "routes":reports,"exported":sum(x["status"]=="AUTHENTICATED_DUAL_PROGRAM_SOURCE_FIXTURE" for x in reports),
             "actionable":False,"live_execution_approved":False,"broadcast":False}
    (root/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps({"exported":summary["exported"],"target":len(selected),"broadcast":False}))
if __name__=="__main__":
    main()
