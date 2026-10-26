"""Meteora DLMM single-bin research quote using authenticated Q64 bin price.

The caller must decode active-bin reserves and fee from the same actual
fork state. This is a bounded one-bin model, NOT a complete DLMM swap.
"""
Q=1<<64
DEN=1000000000

def quote_one_bin(*,amount_in,swap_x_for_y,price_q64,bin_x,bin_y,total_fee_rate,
                  active_bin_id,observed_bin_id):
    fields=(amount_in,price_q64,bin_x,bin_y,total_fee_rate,active_bin_id,observed_bin_id)
    if any(type(v)is not int for v in fields) or not 0<amount_in<2**64:
        raise ValueError("invalid integer DLMM input")
    if not 0<price_q64<1<<128 or bin_x<0 or bin_y<0 or not 0<=total_fee_rate<DEN:
        raise ValueError("invalid bin price/reserves/fee")
    if type(swap_x_for_y)is not bool or active_bin_id!=observed_bin_id:
        raise ValueError("swap direction or active bin not authenticated")
    fee=(amount_in*total_fee_rate+DEN-1)//DEN
    effective=amount_in-fee
    if effective<=0:raise ValueError("fees exhaust DLMM input")
    output=effective*price_q64//Q if swap_x_for_y else effective*Q//price_q64
    capacity=bin_y if swap_x_for_y else bin_x
    if output<=0 or output>capacity:
        raise ValueError("DLMM multi-bin traversal required; refusing partial quote")
    return {"amount_out":output,"fee_input_base_units":fee,
            "one_bin_only":True,"dynamic_fee_source_required":True,
            "protocol_exact_verified":False,"actionable":False,
            "live_execution_approved":False,"broadcast":False}
