"""Conservative Orca Token-2022 quote screen with synchronized tick evidence.

Combines an epoch-anchored pool snapshot, integer input/output transfer fees,
and the existing indicative multi-tick AMM model. NO execution authorization.
"""
from arb.token2022_epoch_observation import scheduled_epoch_snapshot
from arb.token2022_transfer_amounts import net_received
from arb.orca_multitick_quote import quote_from_decoded_arrays

def screen(rpc,address,input_mint,gross_input):
    if type(gross_input) is not int or not 0<gross_input<2**64:
        raise ValueError("invalid input amount")
    observed=scheduled_epoch_snapshot(rpc,address,include_ticks=True)
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
        statuses=[{"start_tick":a.get("start_tick"),"status":a.get("status")}
                  for a in arrays]
        raise ValueError("missing tick coverage: "+
                         f"current_start={current_start} direction="+
                         ("a_to_b" if input_mint==mints[0] else "b_to_a")+
                         f" array_statuses={statuses}") from exc
    gross_output=quote.get("estimated_output_base_units")
    if type(gross_output) is not int or not 0<gross_output<2**64:
        raise ValueError("unusable indicative AMM output")
    after=net_received(observed["mint_accounts"][1-index]["transfer_fee_config"],
                       epoch,gross_output)
    blockers=["AMM_MODEL_NOT_SIMULATION_RECONCILED","TRANSFER_HOOK_ACCOUNTS_NOT_VERIFIED",
              "SIGNED_ATOMIC_SIMULATION_NOT_VERIFIED"]
    blockers += ["MINT_EXTENSION_"+str(kind)+"_UNSUPPORTED_FOR_EXECUTION"
                 for kind in observed["extension_risk"]["blocking_extension_ids"]]
    return {"status":"INDICATIVE_TOKEN2022_QUOTE_ONLY","execution_blockers":blockers,"pool":address,
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
    if "missing or unsupported tick array" in reason or "missing tick coverage" in reason:
        return "TICK_COVERAGE_INCOMPLETE"
    if "429" in reason or "Too Many Requests" in reason:
        return "UPSTREAM_RATE_LIMIT"
    return "OTHER_UNQUOTABLE"

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
            results.append(screen(rpc,address,None,args.gross_input))
        except Exception as exc:
            reason=type(exc).__name__+": "+str(exc)[:180]
            results.append({"pool":address,"status":"UNQUOTABLE",
                            "reason_category":diagnostic_failure_category(reason),
                            "reason":reason,
                            "actionable":False,"executable_quote":False})
    failure_categories={category:sum(x.get("reason_category")==category for x in results)
                        for category in sorted({x.get("reason_category") for x in results if x.get("reason_category")})}
    extension_blocked=sum(bool(x.get("extension_risk",{}).get("blocking_extension_ids")) for x in results)
    report={"checked":len(results),"failure_categories":failure_categories,
            "indicative_with_blocking_mint_extensions":extension_blocked,
            "executable_count":0,
            "indicative_count":sum(x.get("status")=="INDICATIVE_TOKEN2022_QUOTE_ONLY" for x in results),
            "results":results,"actionable":False,"simulation_verified":False,
            "mainnet_broadcast":False}
    Path(args.output).write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!="results"},indent=2))

if __name__=="__main__":
    main()
