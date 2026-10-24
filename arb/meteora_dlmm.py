"""Meteora DLMM LbPair decoder (904 bytes), SPL reserve verification; read-only.

Offsets calculated from MeteoraAg/dlmm-sdk idls/dlmm.json LbPair fields,
including nested bytemuck structs. No quote or swap execution claims.
"""
import base64
from arb.rpc import call
from arb.orca_whirlpool import b58
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
PROGRAM="LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"
SIZE=904
DISC=bytes([33,11,49,98,181,101,177,13])
def decode(raw):
    if len(raw)!=SIZE or raw[:8]!=DISC:raise ValueError("invalid Meteora LbPair account")
    key=lambda off:b58(raw[off:off+32])
    result={"token_x_mint":key(88),"token_y_mint":key(120),
      "reserve_x":key(152),"reserve_y":key(184),
      "oracle":key(552),
      "active_id":int.from_bytes(raw[76:80],"little",signed=True),
      "bin_step":int.from_bytes(raw[80:82],"little"),
      "status":raw[82],"version":raw[882],
      "token_mint_x_program_flag":raw[880],
      "token_mint_y_program_flag":raw[881]}
    if not result["bin_step"] or len(set((result["token_x_mint"],result["token_y_mint"],
         result["reserve_x"],result["reserve_y"])))!=4:
        raise ValueError("invalid DLMM mints, reserves or bin step")
    return result

def verify(rpc,address,state):
    if state["status"]!=0:raise ValueError("DLMM pool not enabled")
    if state["token_mint_x_program_flag"]!=0 or state["token_mint_y_program_flag"]!=0:
        raise ValueError("DLMM token extension unsupported")
    keys=[address,state["reserve_x"],state["reserve_y"]]
    resp=call(rpc,"getMultipleAccounts",[keys,{"encoding":"base64","commitment":"confirmed"}])
    values=resp.get("value")
    slot=resp.get("context",{}).get("slot")
    if type(slot)is not int or slot<0 or not isinstance(values,list) or len(values)!=3:
        raise ValueError("incomplete DLMM synchronized account snapshot")
    pool=values[0]
    if not pool or pool.get("owner")!=PROGRAM or pool.get("executable") or decode(base64.b64decode(
            pool["data"][0],validate=True))!=state:raise ValueError("DLMM pool owner or state mismatch")
    balances=[];authorities=[]
    for i,(mint,idx) in enumerate(((state["token_x_mint"],1),(state["token_y_mint"],2))):
        v=values[idx]
        if not v or v.get("owner")!=TOKEN_PROGRAM or v.get("executable"):raise ValueError("DLMM non-classic SPL vault")
        token=decode_token_account(base64.b64decode(v["data"][0],validate=True))
        if token["mint"]!=mint:raise ValueError("DLMM vault mint mismatch")
        balances.append(token["amount_base_units"])
        authorities.append(token["authority"])
    if min(balances)<=0 or authorities[0]!=authorities[1]:
        raise ValueError("DLMM empty vault or inconsistent authority")
    return {"venue":"meteora_dlmm","address":address,"mints":[state["token_x_mint"],
             state["token_y_mint"]],"vault_base_units":balances,
             "slot":slot,"swap_simulated":False}
