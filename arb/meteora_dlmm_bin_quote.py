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

def quote_bins(*,amount_in,swap_x_for_y,bins,total_fee_rate,max_bins=32):
    """Price a bounded sequence of externally decoded DLMM bins.

    Bins MUST be provided in directional walk order by a source-authenticated
    bin-array decoder. Fee charged independently per consumed input per bin;
    output liquidity capacity is enforced at every step. Refuse partial fills,
    crossed unsupported fee regimes, or exhausted arrays.
    """
    if type(amount_in)is not int or not 0<amount_in<2**64:
        raise ValueError("DLMM positive integer input required")
    if type(swap_x_for_y)is not bool or type(total_fee_rate)is not int or not 0<=total_fee_rate<DEN:
        raise ValueError("DLMM direction or fee invalid")
    if not isinstance(bins,list) or not 1<=len(bins)<=max_bins<=70:
        raise ValueError("DLMM bounded bins missing")
    remaining=amount_in
    output=fees=0
    consumed=[]
    prior=None
    for b in bins:
        if not isinstance(b,dict) or any(type(b.get(k))is not int for k in
                ("bin_id","price_q64","amount_x","amount_y")):
            raise ValueError("DLMM decoded bin missing integer fields")
        idx=b["bin_id"]
        if prior is not None and (idx>=prior if swap_x_for_y else idx<=prior):
            raise ValueError("DLMM bin walk direction invalid")
        prior=idx
        # Dynamic fees may evolve between bin crossings. When independently
        # decoded per-bin rates are available, use each rather than assuming
        # the initial active-bin fee remains valid throughout traversal.
        rate=b.get("effective_fee_rate",total_fee_rate)
        if type(rate)is not int or not 0<=rate<DEN:
            raise ValueError("DLMM invalid per-bin effective fee rate")
        capacity=b["amount_y"] if swap_x_for_y else b["amount_x"]
        price=b["price_q64"]
        if not 0<price<1<<128 or min(b["amount_x"],b["amount_y"])<0:
            raise ValueError("invalid authenticated bin inventory")
        if not capacity:continue
        # Bound input by output-side bin inventory, reducing the guess-and-
        # round problem to monotone exact integer binary search.
        lo,hi=0,remaining
        while lo<hi:
            mid=(lo+hi+1)//2
            fee=(mid*rate+DEN-1)//DEN
            net=mid-fee
            out=net*price//Q if swap_x_for_y else net*Q//price
            if out<=capacity:lo=mid
            else:hi=mid-1
        used=lo
        if used==0:continue
        fee=(used*rate+DEN-1)//DEN
        net=used-fee
        got=net*price//Q if swap_x_for_y else net*Q//price
        if got<=0:continue
        remaining-=used;output+=got;fees+=fee
        consumed.append({"bin_id":idx,"gross_input_base_units":used,
                         "fee_input_base_units":fee,"output_base_units":got,
                         "effective_fee_rate":rate})
        if remaining==0:break
    if remaining or not output:
        raise ValueError("DLMM bin inventory cannot fill complete exact input")
    return {"amount_out":output,"fee_input_base_units":fees,
            "bins_traversed":consumed,"exact_input_filled":True,
            "protocol_exact_verified":False,"actionable":False,
            "live_execution_approved":False,"broadcast":False}
