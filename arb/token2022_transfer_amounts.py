"""Exact integer Token-2022 transfer-fee adjustments for quote screening.

These helpers adjust token transfer amounts only; they cannot establish an
executable Orca swap quote or resolve transfer-hook account metas.
"""
from arb.token2022_extensions import fee_for_epoch

MAX_U64=(1<<64)-1

def net_received(config,epoch,gross_amount):
    if type(gross_amount) is not int or not 0<=gross_amount<=MAX_U64:
        raise ValueError("invalid gross transfer amount")
    if config is None:
        return {"gross_base_units":gross_amount,"fee_base_units":0,
                "net_base_units":gross_amount}
    result=fee_for_epoch(config,epoch,gross_amount)
    return {"gross_base_units":gross_amount,"fee_base_units":result["fee_base_units"],
            "net_base_units":result["net_base_units"]}

def gross_required(config,epoch,net_amount):
    """Smallest gross transfer whose post-fee amount meets target net amount."""
    if type(net_amount) is not int or not 0<=net_amount<=MAX_U64:
        raise ValueError("invalid net transfer amount")
    if config is None:
        return {"requested_net_base_units":net_amount,"gross_base_units":net_amount,
                "fee_base_units":0,"net_base_units":net_amount}
    # Fee monotonicity does not imply net monotonicity when schedules are
    # malformed; fee_for_epoch validates the schedule's rate and bound.
    lo=net_amount
    hi=MAX_U64
    if net_received(config,epoch,hi)["net_base_units"]<net_amount:
        raise ValueError("target net amount cannot be delivered within u64")
    while lo<hi:
        mid=(lo+hi)//2
        if net_received(config,epoch,mid)["net_base_units"]>=net_amount:
            hi=mid
        else:
            lo=mid+1
    output=net_received(config,epoch,lo)
    return {"requested_net_base_units":net_amount,**output}

def transfer_adjusted_pair(input_config,output_config,epoch,source_gross,
                           pool_gross_output):
    """Model token transfer deductions on both pool boundaries, not the AMM."""
    inbound=net_received(input_config,epoch,source_gross)
    outbound=net_received(output_config,epoch,pool_gross_output)
    return {"source_gross_base_units":source_gross,
            "pool_effective_input_base_units":inbound["net_base_units"],
            "input_transfer_fee_base_units":inbound["fee_base_units"],
            "pool_gross_output_base_units":pool_gross_output,
            "recipient_net_output_base_units":outbound["net_base_units"],
            "output_transfer_fee_base_units":outbound["fee_base_units"],
            "amm_quote_verified":False,"executable_quote":False,"actionable":False}
