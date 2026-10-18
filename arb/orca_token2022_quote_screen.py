"""Conservative Orca Token-2022 quote screen with synchronized tick evidence.

Combines an epoch-anchored pool snapshot, integer input/output transfer fees,
and the existing indicative multi-tick AMM model. NO execution authorization.
"""
from arb.token2022_epoch_observation import scheduled_epoch_snapshot
from arb.token2022_transfer_amounts import net_received
from arb.orca_multitick_quote import quote_from_decoded_arrays

def validate_directional_snapshot_accounts(observed,input_mint):
    """Confirm direction mapping only; does not validate instruction account metas."""
    if not isinstance(observed,dict) or not isinstance(observed.get("pool"),dict):
        raise ValueError("invalid synchronized swap account evidence")
    state=observed["pool"]
    mints=observed.get("mints")
    mint_accounts=observed.get("mint_accounts")
    vault_accounts=observed.get("vault_accounts")
    if (not isinstance(mints,list) or len(mints)!=2 or mints[0]==mints[1] or
            input_mint not in mints or not isinstance(mint_accounts,list) or
            len(mint_accounts)!=2 or not isinstance(vault_accounts,list) or
            len(vault_accounts)!=2):
        raise ValueError("invalid synchronized swap pair")
    if [state.get("token_mint_a"),state.get("token_mint_b")]!=mints:
        raise ValueError("synchronized mint identities disagree with pool")
    vaults=[state.get("token_vault_a"),state.get("token_vault_b")]
    if not all(isinstance(v,str) and v for v in vaults) or vaults[0]==vaults[1]:
        raise ValueError("invalid pool vault identities")
    for i in range(2):
        if (not isinstance(mint_accounts[i],dict) or
                not isinstance(vault_accounts[i],dict) or
                vault_accounts[i].get("mint")!=mints[i] or
                vault_accounts[i].get("state")!=1 or
                mint_accounts[i].get("owner") not in (
                    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
                    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")):
            raise ValueError("synchronized vault/mint account mismatch")
    index=mints.index(input_mint)
    return {"input_vault":vaults[index],"output_vault":vaults[1-index],
            "input_token_program":mint_accounts[index]["owner"],
            "output_token_program":mint_accounts[1-index]["owner"],
            "vault_mint_relationships_verified":True,
            "instruction_account_metas_verified":False,"actionable":False}

def directional_tick_array_candidates(state,arrays,a_to_b):
    """Direction-ordered, observed tick arrays; not authenticated SwapV2 metas."""
    from arb.whirlpool_ticks import start_tick, ARRAY_TICKS
    spacing=state["tick_spacing"]
    center=start_tick(state["tick_current_index"],spacing)
    step=spacing*ARRAY_TICKS*(-1 if a_to_b else 1)
    by_start={a["start_tick"]:a for a in arrays
              if isinstance(a,dict) and type(a.get("start_tick")) is int}
    requested=[center+i*step for i in range(3)]
    selected=[by_start.get(start) for start in requested]
    return {"starts":requested,
            "addresses":[a.get("address") if a else None for a in selected],
            "all_present":all(a is not None and a.get("status")=="FIXED_VALID"
                              and isinstance(a.get("address"),str)
                              and bool(a["address"]) for a in selected)
                           and len({a["address"] for a in selected if a})==3,
            "instruction_account_metas_verified":False}

def swap_v2_snapshot_layout_evidence(observed,input_mint,directed_ticks,oracle_pda):
    """Bind observed pool-side accounts to fixed SwapV2 order, never user metas."""
    from arb.orca_swap_v2_metas import ACCOUNT_ROLES
    state=observed["pool"]
    mints=observed["mints"]
    if input_mint not in mints or len(mints)!=2:
        raise ValueError("invalid direction for SwapV2 layout evidence")
    programs=[m.get("owner") for m in observed["mint_accounts"]]
    known={
        "token_program_a":programs[0],"token_program_b":programs[1],
        "whirlpool":observed.get("pool_address"),
        "token_mint_a":mints[0],"token_mint_b":mints[1],
        "token_vault_a":state.get("token_vault_a"),
        "token_vault_b":state.get("token_vault_b"),
        "oracle":oracle_pda,
    }
    for i,address in enumerate(directed_ticks.get("addresses",[])[:3]):
        known[f"tick_array_{i}"]=address
    required=("token_authority","token_owner_account_a","token_owner_account_b")
    missing=[role for role in ACCOUNT_ROLES if role in required or not known.get(role)]
    return {"ordered_roles":list(ACCOUNT_ROLES),
            "observed_pool_side_accounts":known,
            "missing_or_unverified_roles":missing,
            "directional_ticks_complete":bool(directed_ticks.get("all_present")),
            "onchain_account_metas_verified":False,
            "signed_simulation_verified":False,
            "actionable":False,"executable_quote":False,"broadcast":False}

def screen(rpc,address,input_mint,gross_input):
    if type(gross_input) is not int or not 0<gross_input<2**64:
        raise ValueError("invalid input amount")
    observed=scheduled_epoch_snapshot(rpc,address,include_ticks=True,include_oracle=True)
    state=observed["pool"]
    arrays=observed["tick_arrays"]
    if not isinstance(arrays,list) or not arrays:
        raise ValueError("missing synchronized tick-array evidence")
    mints=observed["mints"]
    if input_mint is None and len(mints)==2:
        input_mint=mints[0]  # diagnostic-only default direction
    if input_mint not in mints or len(mints)!=2 or mints[0]==mints[1]:
        raise ValueError("input mint not in distinct pool pair")
    index=mints.index(input_mint)
    epoch=observed["epoch_observation"]["epoch"]
    before=net_received(observed["mint_accounts"][index]["transfer_fee_config"],
                        epoch,gross_input)
    if before["net_base_units"]<=0:
        raise ValueError("input fully consumed by transfer fee")
    try:
        quote=quote_from_decoded_arrays(state,input_mint,before["net_base_units"],
                                        arrays)
    except ValueError as exc:
        if "tick array" not in str(exc) and "tick coverage" not in str(exc):
            raise
        from arb.whirlpool_ticks import start_tick
        current_start=start_tick(state["tick_current_index"],state["tick_spacing"])
        statuses=[{"start_tick":a.get("start_tick"),"address":a.get("address"),
                   "status":a.get("status")}
                  for a in arrays]
        raise ValueError("missing tick coverage: "+
                         f"current_tick={state['tick_current_index']} tick_spacing={state['tick_spacing']} "
                         f"current_start={current_start} direction="+
                         ("a_to_b" if input_mint==mints[0] else "b_to_a")+
                         f" array_statuses={statuses}") from exc
    gross_output=quote.get("estimated_output_base_units")
    if type(gross_output) is not int or not 0<gross_output<2**64:
        raise ValueError("unusable indicative AMM output")
    after=net_received(observed["mint_accounts"][1-index]["transfer_fee_config"],
                       epoch,gross_output)
    mint_execution_evidence=[
        {"mint":mint_address,
         "token_program":mint_obs["owner"],
         "mint_extension_ids":mint_obs["extension_types"],
         "transfer_hook_extension_present":14 in mint_obs["extension_types"],
         "transfer_hook_program_id":mint_obs.get("transfer_hook_program_id"),
         "transfer_hook_program_identity_observed":bool(mint_obs.get("transfer_hook_program_id")),
         "transfer_hook_configuration_status":("PROGRAM_CONFIGURED" if mint_obs.get("transfer_hook_program_id") else "EXTENSION_PRESENT_NO_ACTIVE_PROGRAM" if 14 in mint_obs["extension_types"] else "NO_HOOK_EXTENSION"),
         "transfer_hook_extra_accounts_verified":False,
         "transfer_fee_configured":mint_obs["transfer_fee_config"] is not None,
         "swap_account_metas_verified":False}
        for mint_address,mint_obs in zip(mints,observed["mint_accounts"])]
    directional=validate_directional_snapshot_accounts(observed,input_mint)
    from solders.pubkey import Pubkey
    from arb.orca_whirlpool import PROGRAM
    oracle_pda=str(Pubkey.find_program_address([b"oracle",bytes(Pubkey.from_string(address))],Pubkey.from_string(PROGRAM))[0])
    adaptive_fee_oracle_required=(type(state.get("fee_tier_index_seed")) is int and
                                  type(state.get("tick_spacing")) is int and
                                  state["tick_spacing"]!=state["fee_tier_index_seed"])
    oracle_fee_mode_known=(type(state.get("fee_tier_index_seed")) is int and
                           type(state.get("tick_spacing")) is int)
    directed_ticks=directional_tick_array_candidates(state,arrays,index==0)
    account_candidates={
        "pool":address,"snapshot_slot":observed["slot"],
        "oracle_account_verified":bool((observed.get("oracle_evidence") or {}).get("same_slot_verified")),
        "adaptive_fee_oracle_required":adaptive_fee_oracle_required,
        "oracle_fee_mode_known":oracle_fee_mode_known,
        "oracle_pda_candidate":oracle_pda,
        "oracle_same_slot_evidence":observed.get("oracle_evidence"),
        "input_mint":input_mint,"output_mint":mints[1-index],
        "input_vault":directional["input_vault"],
        "output_vault":directional["output_vault"],
        "input_token_program":directional["input_token_program"],
        "output_token_program":directional["output_token_program"],
        "directional_tick_array_candidates":directed_ticks,
        "swap_v2_layout_evidence":swap_v2_snapshot_layout_evidence(
            {**observed,"pool_address":address},input_mint,directed_ticks,oracle_pda),
        "tick_array_addresses":[a.get("address") for a in arrays],
        "tick_array_statuses":[a.get("status") for a in arrays],
        "tick_array_accounts_present":sum(a.get("status")=="FIXED_VALID" for a in arrays),
        "token_programs_distinct":directional["input_token_program"]!=directional["output_token_program"],
        "vault_mint_relationships_verified":True,
        "instruction_account_metas_verified":False,
        "remaining_accounts_verified":False,"swap_v2_user_token_accounts_verified":False,"swap_v2_authority_verified":False,"swap_v2_oracle_verified":False,"swap_v2_tick_order_verified":False,"actionable":False}
    blockers=["AMM_MODEL_NOT_SIMULATION_RECONCILED",
              "SWAP_ACCOUNT_METAS_NOT_VERIFIED",
              "SIGNED_ATOMIC_SIMULATION_NOT_VERIFIED"]
    if any(m["transfer_hook_configuration_status"]=="PROGRAM_CONFIGURED"
           for m in mint_execution_evidence):
        blockers.append("TRANSFER_HOOK_ACCOUNTS_NOT_VERIFIED")
    blockers += ["MINT_EXTENSION_"+str(kind)+"_UNSUPPORTED_FOR_EXECUTION"
                 for kind in observed["extension_risk"]["blocking_extension_ids"]]
    return {"status":"INDICATIVE_TOKEN2022_QUOTE_ONLY","execution_blockers":blockers,"mint_execution_evidence":mint_execution_evidence,
            "swap_account_candidates":account_candidates,"pool":address,
            "slot":observed["slot"],"epoch":epoch,"input_mint":input_mint,
            "output_mint":mints[1-index],
            "source_gross_input_base_units":gross_input,
            "pool_net_input_base_units":before["net_base_units"],
            "input_transfer_fee_base_units":before["fee_base_units"],
            "pool_gross_output_base_units":gross_output,
            "output_transfer_fee_base_units":after["fee_base_units"],
            "recipient_net_output_base_units":after["net_base_units"],
            "tick_arrays_examined":quote["tick_arrays_examined"],
            "ticks_crossed":quote["ticks_crossed"],
            "extension_risk":observed["extension_risk"],
            "quote_model_verified":False,"transfer_hooks_verified":False,
            "actionable":False,"executable_quote":False,
            "simulation_verified":False,"broadcast":False}

def diagnostic_failure_category(reason):
    """Classify observed failures without interpreting them as quote success."""
    if "epoch observations do not bracket pool snapshot" in reason:
        return "EPOCH_OR_POOL_SLOT_MISMATCH"
    if "stale account snapshot" in reason or "minimum context slot" in reason.lower():
        return "STALE_RPC_CONTEXT"
    if "tick arrays and mint/vault snapshot are not same-slot" in reason:
        return "TICK_SLOT_MISMATCH"
    if "pool changed between mint and tick observations" in reason:
        return "POOL_STATE_CHANGED"
    if ("missing tick coverage:" in reason and
            "current_start=" in reason and "\'status\': \'MISSING\'" in reason):
        return "CURRENT_OR_DIRECTIONAL_TICK_ARRAY_MISSING"
    if "missing or unsupported tick array" in reason or "missing tick coverage" in reason:
        return "TICK_COVERAGE_INCOMPLETE"
    if "429" in reason or "Too Many Requests" in reason:
        return "UPSTREAM_RATE_LIMIT"
    return "OTHER_UNQUOTABLE"

def screen_with_rate_limit_retry(rpc,address,input_mint,gross_input,*,sleeper=None):
    """Retry a whole read-only snapshot only for upstream throttling.

    Never combine partial observations from separate attempts. All other
    failures, including absent tick arrays, remain immediate and fail-closed.
    """
    if sleeper is None:
        import time
        sleeper=time.sleep
    for attempt in range(3):
        try:
            return screen(rpc,address,input_mint,gross_input)
        except Exception as exc:
            if diagnostic_failure_category(str(exc))!="UPSTREAM_RATE_LIMIT" or attempt==2:
                raise
            sleeper(1.5*(attempt+1))

def simple_mint_extension_candidates(results):
    """Read-only prioritization; never returns trade or simulation approval."""
    if not isinstance(results,list):
        raise ValueError("invalid quote results")
    return [{"pool":r["pool"],"slot":r["slot"],
             "status":"INDICATIVE_ONLY_REQUIRES_SWAP_META_AND_SIMULATION",
             "input_mint":r["input_mint"],"output_mint":r["output_mint"],
             "input_token_program":next(m["token_program"] for m in r["mint_execution_evidence"] if m["mint"]==r["input_mint"]),
             "output_token_program":next(m["token_program"] for m in r["mint_execution_evidence"] if m["mint"]==r["output_mint"]),
             "actionable":False,"executable_quote":False,"simulation_verified":False}
            for r in results
            if (isinstance(r,dict) and
                r.get("status")=="INDICATIVE_TOKEN2022_QUOTE_ONLY" and
                r.get("actionable") is False and
                r.get("executable_quote") is False and
                ((r.get("swap_account_candidates") or {}).get("oracle_account_verified") is True or
                 ((r.get("swap_account_candidates") or {}).get("oracle_fee_mode_known") is True and
                  (r.get("swap_account_candidates") or {}).get("adaptive_fee_oracle_required") is False)) and
                isinstance(r.get("pool"),str) and
                type(r.get("slot")) is int and
                isinstance(r.get("mint_execution_evidence"),list) and
                len(r["mint_execution_evidence"])==2 and
                all(isinstance(m,dict) and isinstance(m.get("token_program"),str)
                    and isinstance(m.get("mint"),str)
                    for m in r["mint_execution_evidence"]) and
                {m["mint"] for m in r["mint_execution_evidence"]}==
                {r.get("input_mint"),r.get("output_mint")} and
                r.get("input_mint")!=r.get("output_mint") and
                all(m["token_program"] in (
                    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
                    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
                    for m in r["mint_execution_evidence"]) and
                isinstance(r.get("extension_risk"),dict) and
                r["extension_risk"].get("blocking_extension_ids")==[] and
                isinstance(r.get("execution_blockers"),list) and
                "SWAP_ACCOUNT_METAS_NOT_VERIFIED" in r["execution_blockers"] and
                "SIGNED_ATOMIC_SIMULATION_NOT_VERIFIED" in r["execution_blockers"])]

def main():
    import argparse,json,os
    from pathlib import Path
    p=argparse.ArgumentParser()
    p.add_argument("--cohort",default="arb/orca_token2022_audit_cohort.json")
    p.add_argument("--output",required=True)
    p.add_argument("--limit",type=int,default=3)
    p.add_argument("--gross-input",type=int,default=100000)
    args=p.parse_args()
    if type(args.limit)is not int or not 1<=args.limit<=15:
        raise ValueError("invalid bounded cohort limit")
    if not 0<args.gross_input<=10000000:
        raise ValueError("invalid diagnostic input")
    addresses=json.loads(Path(args.cohort).read_text())["addresses"]
    if not isinstance(addresses,list) or not 1<=len(addresses)<=50 or len(set(addresses))!=len(addresses):
        raise ValueError("invalid cohort")
    rpc=os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899")
    results=[]
    for address in addresses[:args.limit]:
        try:
            results.append(screen_with_rate_limit_retry(rpc,address,None,args.gross_input))
        except Exception as exc:
            reason=type(exc).__name__+": "+str(exc)[:900]
            results.append({"pool":address,"status":"UNQUOTABLE",
                            "reason_category":diagnostic_failure_category(reason),
                            "reason":reason,
                            "actionable":False,"executable_quote":False})
    if any(row.get("actionable") is not False or
           row.get("executable_quote") is not False or
           row.get("simulation_verified") is True or
           row.get("broadcast") is True for row in results):
        raise ValueError("unsafe executable state in diagnostic-only quote report")
    failure_categories={category:sum(x.get("reason_category")==category for x in results)
                        for category in sorted({x.get("reason_category") for x in results if x.get("reason_category")})}
    extension_blocked=sum(bool(x.get("extension_risk",{}).get("blocking_extension_ids")) for x in results)
    hook_pool_count=sum(any(m.get("transfer_hook_extension_present") for m in r.get("mint_execution_evidence",[])) for r in results)
    configured_hook_pools=sum(any(m.get("transfer_hook_configuration_status")=="PROGRAM_CONFIGURED" for m in r.get("mint_execution_evidence",[])) for r in results)
    blocker_counts={name:sum(name in row.get("execution_blockers",[])
                              for row in results)
                    for name in sorted({item for row in results
                                        for item in row.get("execution_blockers",[])})}
    oracle_verified_count=sum(
        r.get("status")=="INDICATIVE_TOKEN2022_QUOTE_ONLY" and
        (r.get("swap_account_candidates") or {}).get("oracle_account_verified") is True
        for r in results)
    simple_candidates=simple_mint_extension_candidates(results)
    report={"checked":len(results),"synchronized_oracle_observed_count":oracle_verified_count,
            "simple_mint_extension_candidates":simple_candidates,
            "execution_blocker_counts":blocker_counts,
            "transfer_hook_pool_count":hook_pool_count,
            "configured_hook_pool_count":configured_hook_pools,"failure_categories":failure_categories,
            "indicative_with_blocking_mint_extensions":extension_blocked,
            "executable_count":0,
            "indicative_count":sum(x.get("status")=="INDICATIVE_TOKEN2022_QUOTE_ONLY" for x in results),
            "results":results,"actionable":False,"simulation_verified":False,
            "mainnet_broadcast":False}
    Path(args.output).write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!="results"},indent=2))

if __name__=="__main__":
    main()
