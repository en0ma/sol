"""Source-authenticated Orca adaptive-fee Oracle account decoder.

Oracle is a genuine pricing input when fee_tier_index_seed differs from
tick_spacing. The 254-byte Borsh layout and field offsets are from the
official Orca Whirlpools client. No guessed fee or dummy Oracle is accepted.
"""
import base64
import hashlib
from arb.orca_whirlpool import PROGRAM,b58

ORACLE_SIZE=254
DISC=hashlib.sha256(b"account:Oracle").digest()[:8]
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def decode_oracle(raw,pool):
    if (not isinstance(raw,bytes) or len(raw)!=ORACLE_SIZE or raw[:8]!=DISC
            or not isinstance(pool,str) or b58(raw[8:40])!=pool):
        raise ValueError("Orca adaptive fee Oracle layout/pool identity mismatch")
    def le(i,n,*,signed=False):
        return int.from_bytes(raw[i:i+n],"little",signed=signed)
    c={"filter_period":le(48,2),"decay_period":le(50,2),
       "reduction_factor":le(52,2),"adaptive_fee_control_factor":le(54,4),
       "max_volatility_accumulator":le(58,4),"tick_group_size":le(62,2),
       "major_swap_threshold_ticks":le(64,2)}
    v={"last_reference_update_timestamp":le(82,8),
       "last_major_swap_timestamp":le(90,8),
       "volatility_reference":le(98,4),
       "tick_group_index_reference":le(102,4,signed=True),
       "volatility_accumulator":le(106,4)}
    if (c["filter_period"]>c["decay_period"] or
            c["reduction_factor"]>10000 or
            not c["tick_group_size"] or
            not c["max_volatility_accumulator"] or
            v["volatility_reference"]>c["max_volatility_accumulator"] or
            v["volatility_accumulator"]>c["max_volatility_accumulator"]):
        raise ValueError("invalid authenticated Orca adaptive fee constants/variables")
    return {"pool":pool,"trade_enable_timestamp":le(40,8),
            "constants":c,"variables":v,
            "oracle_layout_authenticated":True,
            "effective_adaptive_fee_math_verified":False,**SAFE}

def source_oracle(fixture,pool,state):
    if not isinstance(state,dict) or not isinstance(fixture,dict):
        raise ValueError("authenticated Orca pool source state required")
    if state.get("fee_tier_index_seed")==state.get("tick_spacing"):
        return None
    evidence=fixture.get("leg_evidence_by_index")
    if not isinstance(evidence,list):
        raise ValueError("Orca adaptive fee source Oracle inventory absent")
    matching=[row for row in evidence if isinstance(row,dict) and
              row.get("venue")=="orca" and row.get("pool")==pool]
    if len(matching)!=1:
        raise ValueError("ambiguous Orca source Oracle relationship")
    address=matching[0].get("auxiliary",{}).get("oracle")
    if (not isinstance(address,str) or
            address not in fixture.get("state_account_addresses",[]) or
            fixture["state_account_addresses"].count(address)!=1):
        raise ValueError("Orca adaptive Oracle absent from source inventory")
    info=fixture.get("accounts",{}).get(address)
    if not isinstance(info,dict) or info.get("owner")!=PROGRAM or info.get("executable") is not False:
        raise ValueError("Orca adaptive Oracle owner or executable mismatch")
    data=info.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("Orca adaptive Oracle bytes unavailable")
    return {"oracle_address":address,
            **decode_oracle(base64.b64decode(data[0],validate=True),pool)}

def quote_adaptive_from_arrays(state,mint_in,amount_in,arrays,oracle,*,observed_unix):
    """Exact-input source-native Whirlpool adaptive fee/group tick traversal.

    Reimplements Orca FeeRateManager's reference decay, volatility accumulator,
    ceil dynamic rate and tick-group boundary steps on integer Q64 prices.
    Only operates within contiguous authenticated source arrays. Unobserved
    liquidity boundaries fail closed rather than inventing zero-liquidity ticks.
    """
    from arb.orca_tick_math import sqrt_price_from_tick_index
    from arb.whirlpool_ticks import ARRAY_TICKS,start_tick
    if (not isinstance(oracle,dict) or oracle.get("oracle_layout_authenticated") is not True
            or any(oracle.get(k)is not False for k in SAFE)
            or type(observed_unix)is not int or observed_unix<0):
        raise ValueError("authenticated adaptive fee oracle and fork clock required")
    if type(amount_in)is not int or not 0<amount_in<2**64:
        raise ValueError("u64 source exact-input amount required")
    if mint_in not in (state["token_mint_a"],state["token_mint_b"]):
        raise ValueError("Orca source mint does not match pool")
    down=mint_in==state["token_mint_a"]
    liquidity=int(state["liquidity"])
    price=int(state["sqrt_price_x64"])
    current_tick=state["tick_current_index"]
    spacing=state["tick_spacing"]
    fee=state["fee_rate_hundredths_bps"]
    if not 0<liquidity<2**128 or not 0<price<2**128 or not 0<=fee<100000:
        raise ValueError("invalid source Whirlpool liquidity, price or base fee")
    if type(current_tick)is not int or type(spacing)is not int or spacing<=0:
        raise ValueError("invalid Whirlpool tick metadata")
    if not isinstance(arrays,list) or not 1<=len(arrays)<=9:
        raise ValueError("authenticated source Whirlpool arrays required")
    span=ARRAY_TICKS*spacing
    start=start_tick(current_tick,spacing)
    by_start={}
    for array in arrays:
        if (not isinstance(array,dict) or
                array.get("status") not in ("FIXED_VALID","DYNAMIC_VALID") or
                type(array.get("start_tick"))is not int or
                array["start_tick"]%span or array["start_tick"] in by_start or
                not isinstance(array.get("ticks"),list)):
            raise ValueError("invalid source tick array layout or duplicate start")
        by_start[array["start_tick"]]=array
    if start not in by_start:
        raise ValueError("Whirlpool current tick array missing")
    contiguous=[]
    while start in by_start:
        contiguous.append(by_start[start])
        start+=-span if down else span
    ticks={}
    for array in contiguous:
        begin=array["start_tick"]
        for record in array["ticks"]:
            idx=record.get("tick_index")
            net=record.get("liquidity_net")
            if (type(idx)is not int or not begin<=idx<begin+span or
                    (idx-begin)%spacing or idx in ticks or
                    not isinstance(net,str) or not net.lstrip("-").isdigit()):
                raise ValueError("invalid source initialized Whirlpool tick")
            if idx<=current_tick if down else idx>current_tick:
                ticks[idx]=int(net)
    # A missing source array is a hard price boundary, not a zero-liquidity tick.
    extreme=(contiguous[-1]["start_tick"] if down else
             contiguous[-1]["start_tick"]+span-1)
    if not -443636<=extreme<=443636:
        raise ValueError("Whirlpool authenticated source coverage out of bounds")
    end_price=sqrt_price_from_tick_index(extreme)
    if not (end_price<price if down else end_price>price):
        raise ValueError("source tick coverage has no trade direction")
    const=oracle["constants"]
    v=oracle["variables"]
    tick_group_size=const["tick_group_size"]
    if not 1<=tick_group_size<=443636:
        raise ValueError("invalid adaptive fee tick group")
    group=current_tick//tick_group_size
    ref_group=v["tick_group_index_reference"]
    ref_vol=v["volatility_reference"]
    latest=max(v["last_reference_update_timestamp"],v["last_major_swap_timestamp"])
    if observed_unix<latest:
        raise ValueError("fork observation clock precedes Oracle reference")
    age=observed_unix-v["last_reference_update_timestamp"]
    elapsed=observed_unix-latest
    if age>3600 or elapsed>=const["decay_period"]:
        ref_group=group
        ref_vol=0
    elif elapsed>=const["filter_period"]:
        ref_group=group
        ref_vol=v["volatility_accumulator"]*const["reduction_factor"]//10000
    Q=1<<64
    DEN=1000000
    remaining=amount_in
    output=0
    trace=[]
    crossed=[]
    current_index=current_tick
    for _ in range(512):
        if remaining==0:
            break
        vol=min(const["max_volatility_accumulator"],
                ref_vol+abs(group-ref_group)*10000)
        scaled=vol*tick_group_size
        dynamic=min(100000,(const["adaptive_fee_control_factor"]*scaled*scaled+
                            100000*10000*10000-1)//(100000*10000*10000))
        rate=min(100000,fee+dynamic)
        if rate>=DEN:
            raise ValueError("effective adaptive fee exceeds exact-input denominator")
        candidates=([idx for idx in ticks if idx<=current_index] if down
                    else [idx for idx in ticks if idx>current_index])
        initialized_index=(max(candidates) if down else min(candidates)) if candidates else None
        initialized_price=(sqrt_price_from_tick_index(initialized_index)
                           if initialized_index is not None else end_price)
        # Bound by the known array limit AND the nearest true initialized tick.
        if down:
            initialized_price=max(initialized_price,end_price)
            group_tick=max(-443636,group*tick_group_size)
            group_price=sqrt_price_from_tick_index(group_tick)
            target=max(initialized_price,group_price)
        else:
            initialized_price=min(initialized_price,end_price)
            group_tick=min(443636,(group+1)*tick_group_size)
            group_price=sqrt_price_from_tick_index(group_tick)
            target=min(initialized_price,group_price)
        if not (target<=price if down else target>=price):
            raise ValueError("source adaptive swap target reverses price")
        if target==price:
            spent=0
            next_price=price
            out_step=0
            reached=True
        else:
            needed=((liquidity*Q*(price-target)+(price*target)-1)//
                    (price*target) if down else
                    (liquidity*(target-price)+Q-1)//Q)
            effective=remaining*(DEN-rate)//DEN
            reached=needed<=effective
            if reached:
                net=needed
                spent=net+(net*rate+DEN-rate-1)//(DEN-rate)
                next_price=target
            else:
                net=effective
                spent=remaining
                if net<=0:
                    raise ValueError("all adaptive exact input consumed by fees")
                next_price=((liquidity*Q*price+liquidity*Q+net*price-1)//
                            (liquidity*Q+net*price) if down else
                            price+net*Q//liquidity)
                if not (target<next_price<price if down else
                        price<next_price<target):
                    raise ValueError("adaptive partial swap target boundary mismatch")
            if not 0<=spent<=remaining:
                raise ValueError("adaptive fee amount underflow")
            out_step=(liquidity*(price-next_price)//Q if down else
                      liquidity*Q*(next_price-price)//(price*next_price))
        if next_price==end_price and remaining>spent:
            raise ValueError("Orca source arrays exhausted before exact input")
        remaining-=spent
        output+=out_step
        trace.append({"fee_rate_ppm":rate,"dynamic_fee_rate_ppm":dynamic,
                      "volatility_accumulator":vol,"tick_group_index":group,
                      "gross_input_base_units":spent,"output_base_units":out_step,
                      "end_sqrt_price_x64":str(next_price)})
        price=next_price
        if reached and initialized_index is not None and price==initialized_price:
            after=(liquidity-ticks[initialized_index] if down else
                   liquidity+ticks[initialized_index])
            if not 0<after<2**128 and remaining:
                raise ValueError("Whirlpool initialized crossing exhausted liquidity")
            liquidity=after
            crossed.append(initialized_index)
            current_index=initialized_index-1 if down else initialized_index
            ticks.pop(initialized_index)
        if reached and price==group_price:
            group+=-1 if down else 1
        if not reached:
            break
        if remaining and price==end_price:
            raise ValueError("Orca source price array boundary reached")
    else:
        raise ValueError("adaptive fee crossing iteration budget exceeded")
    if remaining or not 0<output<2**64:
        raise ValueError("Orca adaptive fee source model could not fully fill")
    return {"status":"SOURCE_ORCA_ADAPTIVE_FEE_NATIVE_INTEGER_QUOTE",
            "amount_in":amount_in,"estimated_output_base_units":output,
            "signed_source_quote_exact_verified":False,
            "crossed_initialized_ticks":crossed,"adaptive_fee_steps":trace,
            "source_oracle_decoded":True,
            "actionable":False,"broadcast":False,"live_execution_approved":False}
