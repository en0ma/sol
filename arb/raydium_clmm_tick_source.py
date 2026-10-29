"""Authenticated Raydium CLMM tick-array capture for sixth-venue pricing.

Bounded sparse tick arrays on BOTH sides of the source's active tick.
Uses official Raydium PDA seed and packed tick-array layout. Source-only:
a tick array snapshot is NOT an executable, SDK-parity or signed receipt.
"""
import base64
import hashlib
from solders.pubkey import Pubkey
from arb.rpc import call
from arb.raydium_clmm import PROGRAM,decode as decode_pool
from arb.orca_whirlpool import b58

TICKS_PER_ARRAY=60
TICK_STATE_LEN=168
TICK_ARRAY_LEN=8+32+4+60*TICK_STATE_LEN+1+115
DISC=hashlib.sha256(b"account:TickArrayState").digest()[:8]

def array_start(tick,spacing):
    if type(tick) is not int or type(spacing) is not int or spacing<=0 or spacing>32767:
        raise ValueError("CLMM tick array start arguments invalid")
    return (tick//(spacing*TICKS_PER_ARRAY))*(spacing*TICKS_PER_ARRAY)

def tick_array_pda(pool,start):
    if type(start) is not int or not -(1<<31)<=start<1<<31:
        raise ValueError("CLMM tick array start out of signed 32-bit range")
    return str(Pubkey.find_program_address([
        b"tick_array",bytes(Pubkey.from_string(pool)),
        start.to_bytes(4,"big",signed=True)],Pubkey.from_string(PROGRAM))[0])

def decode_tick_array(raw,pool,start,spacing):
    if len(raw)!=TICK_ARRAY_LEN or raw[:8]!=DISC:
        raise ValueError("CLMM tick array discriminator or length invalid")
    if b58(raw[8:40])!=pool or int.from_bytes(raw[40:44],"little",signed=True)!=start:
        raise ValueError("CLMM tick-array pool or index disagrees with PDA")
    if array_start(start,spacing)!=start:
        raise ValueError("CLMM tick-array index misaligned")
    lp_ticks=[]
    order_ticks=[]
    for i in range(60):
        off=44+i*TICK_STATE_LEN
        tick=int.from_bytes(raw[off:off+4],"little",signed=True)
        net=int.from_bytes(raw[off+4:off+20],"little",signed=True)
        gross=int.from_bytes(raw[off+20:off+36],"little")
        order_phase=int.from_bytes(raw[off+116:off+124],"little")
        orders_amount=int.from_bytes(raw[off+124:off+132],"little")
        part_filled=int.from_bytes(raw[off+132:off+140],"little")
        initialized=bool(gross or orders_amount or part_filled)
        if initialized and tick!=start+i*spacing:
            raise ValueError("CLMM initialized tick position invalid")
        if gross:
            lp_ticks.append({"tick":tick,"liquidity_net":str(net),
                             "liquidity_gross":str(gross)})
        if orders_amount or part_filled:
            order_ticks.append({"tick":tick,"order_phase":str(order_phase),
                "orders_amount":str(orders_amount),
                "part_filled_orders_remaining":str(part_filled),
                "unfilled_ratio_x64":str(int.from_bytes(raw[off+140:off+156],"little"))})
    initialized_count=raw[44+60*TICK_STATE_LEN]
    combined={r["tick"] for r in lp_ticks}|{r["tick"] for r in order_ticks}
    if initialized_count!=len(combined):
        raise ValueError("CLMM initialized count differs from LP and limit-order union")
    return {"pool":pool,"start_tick_index":start,
            "initialized_tick_count":initialized_count,
            "initialized_lp_tick_count":len(lp_ticks),
            "additional_initialized_non_lp_ticks":len(combined)-len(lp_ticks),
            "initialized_ticks":lp_ticks,"limit_order_ticks":order_ticks}

def capture_tick_arrays(rpc,pool,state,*,radius=4):
    if type(radius) is not int or not 1<=radius<=8:
        raise ValueError("bounded CLMM array neighborhood required")
    if not isinstance(state,dict) or state.get("liquidity",0)<=0:
        raise ValueError("CLMM verified pool state required")
    step=state["tick_spacing"]*TICKS_PER_ARRAY
    center=array_start(state["tick_current"],state["tick_spacing"])
    starts=[center+i*step for i in range(-radius,radius+1)]
    addresses=[tick_array_pda(pool,start) for start in starts]
    response=call(rpc,"getMultipleAccounts",[[
        pool,*addresses],{"encoding":"base64","commitment":"confirmed"}])
    slot=response.get("context",{}).get("slot")
    accounts=response.get("value")
    if (type(slot) is not int or slot<0 or not isinstance(accounts,list)
            or len(accounts)!=len(addresses)+1):
        raise ValueError("CLMM same-slot tick array snapshot incomplete")
    pool_account=accounts[0]
    if (not isinstance(pool_account,dict) or pool_account.get("owner")!=PROGRAM
            or decode_pool(base64.b64decode(pool_account["data"][0],validate=True))!=state):
        raise ValueError("CLMM pool price/fee state changed across tick-array read")
    rows=[]
    for start,address,account in zip(starts,addresses,accounts[1:]):
        if account is None:
            rows.append({"address":address,"start_tick_index":start,"present":False})
            continue
        if account.get("owner")!=PROGRAM or account.get("executable") is not False:
            raise ValueError("CLMM tick array program owner mismatch")
        encoded=account["data"][0]
        raw=base64.b64decode(encoded,validate=True)
        if base64.b64encode(raw).decode()!=encoded:
            raise ValueError("CLMM tick array noncanonical bytes")
        decoded=decode_tick_array(raw,pool,start,state["tick_spacing"])
        rows.append({**decoded,"address":address,"present":True,
            "lamports":account["lamports"],"owner":PROGRAM,
            "account_base64":encoded})
    if not any(r["present"] for r in rows):
        raise ValueError("CLMM no authenticated initialized tick-array accounts")
    return {"pool":pool,"tick_array_source_slot":slot,
        "tick_array_pool_data_base64":pool_account["data"][0],
        "tick_arrays":rows,"arrays_present":sum(r["present"] for r in rows),
        "native_pricing_verified":False,"signed_parity_verified":False,
        "actionable":False,"broadcast":False}
