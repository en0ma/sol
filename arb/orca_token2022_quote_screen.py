"""Conservative Orca Token-2022 quote screen with synchronized tick evidence.

Combines an epoch-anchored pool snapshot, integer input/output transfer fees,
and the existing indicative multi-tick AMM model. NO execution authorization.
"""
from arb.token2022_epoch_observation import epoch_anchored_snapshot
from arb.token2022_transfer_amounts import net_received
from arb.whirlpool_ticks import inspect
from arb.orca_multitick_quote import quote_from_decoded_arrays

def screen(rpc,address,input_mint,gross_input):
    if type(gross_input) is not int or not 0<gross_input<2**64:
        raise ValueError("invalid input amount")
    observed=epoch_anchored_snapshot(rpc,address)
    ticks=inspect(rpc,address)
    state=observed["pool"]
    if ticks.get("pool")!=address or ticks.get("pool_state")!=state:
        raise ValueError("pool changed between mint and tick observations")
    if type(ticks.get("slot")) is not int or ticks["slot"]!=observed["slot"]:
        raise ValueError("tick arrays and mint/vault snapshot are not same-slot")
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
    quote=quote_from_decoded_arrays(state,input_mint,before["net_base_units"],
                                    ticks["arrays"])
    gross_output=quote.get("estimated_output_base_units")
    if type(gross_output) is not int or not 0<gross_output<2**64:
        raise ValueError("unusable indicative AMM output")
    after=net_received(observed["mint_accounts"][1-index]["transfer_fee_config"],
                       epoch,gross_output)
    return {"status":"INDICATIVE_TOKEN2022_QUOTE_ONLY","pool":address,
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
            results.append({"pool":address,"status":"UNQUOTABLE",
                            "reason":type(exc).__name__+": "+str(exc)[:180],
                            "actionable":False,"executable_quote":False})
    report={"checked":len(results),
            "indicative_count":sum(x.get("status")=="INDICATIVE_TOKEN2022_QUOTE_ONLY" for x in results),
            "results":results,"actionable":False,"simulation_verified":False,
            "mainnet_broadcast":False}
    Path(args.output).write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!="results"},indent=2))

if __name__=="__main__":
    main()
