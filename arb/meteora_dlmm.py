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
# LbPair repr(C) offsets from MeteoraAg/dlmm-sdk idls/dlmm.json,
# after the eight-byte Anchor discriminator. Activation checks are independent
# of ordinary pool authentication and never authorize live execution.
def swap_activation_evidence(state, *, slot, unix_timestamp, swap_initiator=None):
    if (not isinstance(state,dict) or type(slot)is not int or slot<0
            or type(unix_timestamp)is not int or unix_timestamp<0):
        raise ValueError("authenticated DLMM state and source clock required")
    pair_type=state.get("pair_type")
    activation_type=state.get("activation_type")
    point=state.get("activation_point")
    if (type(pair_type)is not int or pair_type not in (0,1,2,3)
            or type(activation_type)is not int or activation_type not in (0,1)
            or type(point)is not int or point<0):
        raise ValueError("unsupported DLMM activation fields")
    if state.get("status")!=0:
        return {"swap_eligible":False,"reason":"POOL_STATUS_DISABLED",
                "source_slot":slot,"source_unix_timestamp":unix_timestamp}
    if pair_type in (0,3):
        return {"swap_eligible":True,"reason":"PERMISSIONLESS_STATUS_ENABLED",
                "source_slot":slot,"source_unix_timestamp":unix_timestamp}
    now=slot if activation_type==0 else unix_timestamp
    if now>=point:
        return {"swap_eligible":True,"reason":"ACTIVATION_POINT_REACHED",
                "source_slot":slot,"source_unix_timestamp":unix_timestamp,
                "activation_type":activation_type,"activation_point":point}
    early=state.get("pre_activation_swap_address")
    duration=state.get("pre_activation_duration")
    if (swap_initiator is not None and isinstance(early,str)
            and swap_initiator==early and type(duration)is int
            and duration>=0 and now>=max(0,point-duration)):
        return {"swap_eligible":True,"reason":"SOURCE_AUTHENTICATED_PRE_ACTIVATION_SIGNER",
                "source_slot":slot,"source_unix_timestamp":unix_timestamp,
                "activation_type":activation_type,"activation_point":point}
    return {"swap_eligible":False,"reason":"ACTIVATION_PENDING_UNAUTHORIZED_SIGNER",
            "source_slot":slot,"source_unix_timestamp":unix_timestamp,
            "activation_type":activation_type,"activation_point":point}

def decode(raw):
    if len(raw)!=SIZE or raw[:8]!=DISC:raise ValueError("invalid Meteora LbPair account")
    key=lambda off:b58(raw[off:off+32])
    result={"token_x_mint":key(88),"token_y_mint":key(120),
      "reserve_x":key(152),"reserve_y":key(184),
      "oracle":key(552),
      "active_id":int.from_bytes(raw[76:80],"little",signed=True),
      "bin_step":int.from_bytes(raw[80:82],"little"),
      "status":raw[82],"version":raw[882],
      "pair_type":raw[75],"activation_type":raw[86],
      "pre_activation_swap_address":key(752),
      "activation_point":int.from_bytes(raw[816:824],"little"),
      "pre_activation_duration":int.from_bytes(raw[824:832],"little"),
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
