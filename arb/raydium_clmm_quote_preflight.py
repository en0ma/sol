"""Fail-closed Raydium CLMM amount-aware quote probe on real Surfpool data.

Reads an authenticated pool+fee snapshot and verifies candidate tick arrays in
the same RPC response. Tick-array presence does NOT establish the next
initialized tick or usable liquidity path, so no quote is certified yet.
"""
import base64
from arb.rpc import call
from arb.raydium_clmm import PROGRAM,decode
from arb.raydium_clmm_ticks import tick_array_pda,start_tick,SIZE,DISC
from arb.orca_whirlpool import b58
from arb.raydium_clmm_fee_snapshot import read


def inspect_authenticated(rpc,pool,zero_for_one):
    if type(zero_for_one) is not bool:raise ValueError("invalid CLMM direction")
    fee=read(rpc,pool)
    state=fee["state"]
    start=start_tick(state["tick_current"],state["tick_spacing"])
    keys=[tick_array_pda(pool,start)]
    response=call(rpc,"getMultipleAccounts",[
        [pool,fee["amm_config"],*keys],{"encoding":"base64","commitment":"confirmed"}])
    slot=response.get("context",{}).get("slot")
    accounts=response.get("value")
    if type(slot) is not int or not isinstance(accounts,list) or len(accounts)!=3:
        raise ValueError("missing synchronized CLMM quote inputs")
    raw=base64.b64decode(accounts[0]["data"][0],validate=True)
    current=decode(raw)
    if current!=state or slot<fee["slot"]:
        raise ValueError("CLMM pool state changed or slot regressed")
    fee_account=accounts[1]
    if not fee_account or fee_account.get("owner")!=PROGRAM:
        raise ValueError("unauthenticated CLMM fee account")
    from arb.raydium_clmm_fee_snapshot import DISC as CONFIG_DISC
    config=base64.b64decode(fee_account["data"][0],validate=True)
    if (len(config)<53 or config[:8]!=CONFIG_DISC or
            int.from_bytes(config[47:51],"little")!=fee["trade_fee_rate_ppm"] or
            int.from_bytes(config[51:53],"little")!=state["tick_spacing"]):
        raise ValueError("CLMM fee config changed")
    info=accounts[2]
    if not info or info.get("owner")!=PROGRAM or info.get("executable"):
        raise ValueError("missing current CLMM tick array")
    raw_tick=base64.b64decode(info["data"][0],validate=True)
    if (len(raw_tick)!=SIZE or raw_tick[:8]!=DISC or
            b58(raw_tick[8:40])!=pool or
            int.from_bytes(raw_tick[40:44],"little",signed=True)!=start):
        raise ValueError("unauthenticated current CLMM tick array")
    return {"status":"FEE_AND_CURRENT_ARRAY_AUTHENTICATED",
        "pool":pool,"slot":slot,"fee_rate_ppm":fee["trade_fee_rate_ppm"],
        "direction":"zero_for_one" if zero_for_one else "one_for_zero",
        "current_array":keys[0],"quote_available":False,
        "simulation_verified":False,"actionable":False}
