"""Meteora DAMM v2 Pool account decoder, with strict classic SPL reserve checks.

Offsets/1112 bytes from official damm-v2-sdk/src/idl/cp_amm.json
bytemuck Pool; no swap execution or price quote is implied.
"""
import base64
from arb.rpc import call
from arb.orca_whirlpool import b58
from arb.token_vaults import decode_token_account,TOKEN_PROGRAM
PROGRAM="cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"
SIZE=1112
DISC=bytes([241,154,109,4,17,177,109,188])
def decode(raw):
    if len(raw)!=SIZE or raw[:8]!=DISC:raise ValueError("invalid DAMM v2 Pool layout")
    key=lambda n:b58(raw[n:n+32])
    data={"token_a_mint":key(168),"token_b_mint":key(200),
          "token_a_vault":key(232),"token_b_vault":key(264),
          "liquidity":int.from_bytes(raw[360:376],"little"),
          "sqrt_price":int.from_bytes(raw[456:472],"little"),
          "activation_point":int.from_bytes(raw[472:480],"little"),
          "activation_type":raw[480],"pool_status":raw[481],
          "token_a_flag":raw[482],"token_b_flag":raw[483],
          "layout_version":raw[696]}
    if not data["sqrt_price"] or len({data["token_a_mint"],data["token_b_mint"],
          data["token_a_vault"],data["token_b_vault"]})!=4:
        raise ValueError("invalid DAMM v2 pool price or mints")
    return data

def verify(rpc,address,state):
    if state["pool_status"]!=0:raise ValueError("DAMM v2 pool disabled")
    if state["token_a_flag"] or state["token_b_flag"]:
        raise ValueError("DAMM v2 non-classic token flags unsupported")
    addresses=[address,state["token_a_vault"],state["token_b_vault"]]
    reply=call(rpc,"getMultipleAccounts",[addresses,{"encoding":"base64","commitment":"confirmed"}])
    values=reply.get("value")
    slot=reply.get("context",{}).get("slot")
    if type(slot)is not int or slot<0 or not isinstance(values,list) or len(values)!=3:
        raise ValueError("incomplete DAMM v2 synchronized account snapshot")
    pool=values[0]
    if not pool or pool.get("owner")!=PROGRAM or pool.get("executable") or decode(base64.b64decode(
        pool["data"][0],validate=True))!=state:raise ValueError("DAMM v2 pool changed")
    balances=[];auth=[]
    for key,entry in zip(("token_a_mint","token_b_mint"),values[1:]):
        if not entry or entry.get("owner")!=TOKEN_PROGRAM or entry.get("executable"):raise ValueError("unsupported SPL vault")
        token=decode_token_account(base64.b64decode(entry["data"][0],validate=True))
        if token["mint"]!=state[key]:raise ValueError("DAMM v2 vault mint mismatch")
        balances.append(token["amount_base_units"]);auth.append(token["authority"])
    if min(balances)<=0 or auth[0]!=auth[1] or state["liquidity"]<=0:
        raise ValueError("DAMM v2 reserves, authority or liquidity invalid")
    return {"venue":"meteora_damm_v2","address":address,
            "mints":[state["token_a_mint"],state["token_b_mint"]],
            "vault_base_units":balances,
            "slot":slot,"swap_simulated":False}
