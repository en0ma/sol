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
