"""Read-only fee-boundary assessment for epoch-anchored Orca Token-2022 pools.

The AMM quote, transfer hooks, tick arrays and signed simulation remain
unverified. Never use this report to authorize a swap.
"""
from arb.token2022_epoch_observation import epoch_anchored_snapshot
from arb.token2022_transfer_amounts import net_received, gross_required

def assess(rpc,address,source_mint,gross_input,pool_gross_output):
    if (type(gross_input)is not int or type(pool_gross_output)is not int or
            gross_input<0 or pool_gross_output<0):
        raise ValueError("invalid transfer amounts")
    state=epoch_anchored_snapshot(rpc,address)
    mints=state["mints"]
    if source_mint not in mints or len(mints)!=2 or mints[0]==mints[1]:
        raise ValueError("input mint does not identify a distinct pool token")
    source=mints.index(source_mint)
    target=1-source
    epoch=state["epoch_observation"]["epoch"]
    input_fee=state["mint_accounts"][source]["transfer_fee_config"]
    output_fee=state["mint_accounts"][target]["transfer_fee_config"]
    inbound=net_received(input_fee,epoch,gross_input)
    outbound=net_received(output_fee,epoch,pool_gross_output)
    inverse=gross_required(output_fee,epoch,outbound["net_base_units"])
    return {"address":address,"slot":state["slot"],"epoch":epoch,
            "input_mint":mints[source],"output_mint":mints[target],
            "source_gross_base_units":gross_input,
            "pool_net_input_base_units":inbound["net_base_units"],
            "input_transfer_fee_base_units":inbound["fee_base_units"],
            "pool_gross_output_base_units":pool_gross_output,
            "recipient_net_output_base_units":outbound["net_base_units"],
            "output_transfer_fee_base_units":outbound["fee_base_units"],
            "minimum_gross_for_observed_net":inverse["gross_base_units"],
            "extension_risk":state["extension_risk"],
            "amm_quote_verified":False,"transfer_hook_accounts_verified":False,
            "executable_quote":False,"actionable":False,
            "simulation_verified":False,"broadcast":False}
