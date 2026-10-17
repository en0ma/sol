"""Strict Token-2022 token-account and mint extension inventory.

Structural decoding is not swap eligibility. Unknown or fee-affecting extensions
must never be treated as an executable quote.
"""
from arb.orca_whirlpool import b58
from arb.token_vaults import TOKEN_PROGRAM, decode_token_account

TOKEN_2022="TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
ACCOUNT_TYPE_MINT=1
ACCOUNT_TYPE_ACCOUNT=2

def extension_types(raw,account_type):
    if not isinstance(raw,bytes) or len(raw)<166 or raw[165]!=account_type:
        raise ValueError("invalid Token-2022 account type or size")
    result=[]
    offset=166
    while offset<len(raw):
        tail=raw[offset:]
        if not any(tail):
            break
        if len(tail)<4:
            raise ValueError("truncated Token-2022 extension header")
        kind=int.from_bytes(tail[:2],"little")
        size=int.from_bytes(tail[2:4],"little")
        if kind==0:
            if any(tail):
                raise ValueError("unexpected uninitialized TLV payload")
            break
        if kind in result or offset+4+size>len(raw):
            raise ValueError("duplicate or truncated Token-2022 extension")
        result.append(kind)
        offset+=4+size
    return result

def account_observation(owner,raw):
    if owner==TOKEN_PROGRAM:
        decoded=decode_token_account(raw)
        return {**decoded,"token_program":"classic","extension_types":[],
                "execution_eligible":True}
    if owner!=TOKEN_2022:
        raise ValueError("unsupported token account owner")
    if len(raw)<165 or raw[108]!=1:
        raise ValueError("uninitialized or truncated Token-2022 account")
    types=[] if len(raw)==165 else extension_types(raw,ACCOUNT_TYPE_ACCOUNT)
    return {"mint":b58(raw[:32]),"authority":b58(raw[32:64]),
            "amount_base_units":int.from_bytes(raw[64:72],"little"),
            "state":raw[108],"token_program":"token_2022",
            "extension_types":types,"execution_eligible":False}

def transfer_fee_config(raw):
    """Parse authenticated mint TLV type 1; never infer the active epoch."""
    if not isinstance(raw,bytes) or len(raw)<166 or raw[165]!=ACCOUNT_TYPE_MINT:
        raise ValueError("invalid Token-2022 mint")
    offset=166
    found=None
    while offset<len(raw):
        tail=raw[offset:]
        if not any(tail):
            break
        if len(tail)<4:
            raise ValueError("truncated mint TLV")
        kind=int.from_bytes(tail[:2],"little")
        size=int.from_bytes(tail[2:4],"little")
        if kind==0 or offset+4+size>len(raw):
            raise ValueError("invalid mint TLV")
        if kind==1:
            if found is not None or size!=108:
                raise ValueError("duplicate or invalid transfer-fee config")
            payload=raw[offset+4:offset+4+size]
            def schedule(start):
                epoch=int.from_bytes(payload[start:start+8],"little")
                maximum=int.from_bytes(payload[start+8:start+16],"little")
                basis_points=int.from_bytes(payload[start+16:start+18],"little")
                if basis_points>10000:
                    raise ValueError("transfer fee basis points exceed 10000")
                return {"epoch":epoch,"maximum_fee":maximum,
                        "basis_points":basis_points}
            found={"withheld_amount":int.from_bytes(payload[64:72],"little"),
                   "older":schedule(72),"newer":schedule(90),
                   "fee_epoch_authenticated":False,
                   "executable_quote":False}
        offset+=4+size
    return found

def fee_for_epoch(config,epoch,amount):
    """Integer fee for known epoch and gross transfer amount; not swap readiness."""
    if (not isinstance(config,dict) or type(epoch)is not int or epoch<0 or
            type(amount)is not int or not 0<=amount<2**64):
        raise ValueError("invalid transfer-fee inputs")
    schedule=config["newer"] if epoch>=config["newer"]["epoch"] else config["older"]
    if epoch<schedule["epoch"]:
        raise ValueError("fee schedule epoch unavailable")
    bps=schedule["basis_points"]
    if type(bps)is not int or not 0<=bps<=10000:
        raise ValueError("invalid basis points")
    maximum=schedule["maximum_fee"]
    if type(maximum)is not int or maximum<0:
        raise ValueError("invalid maximum fee")
    fee=min(maximum,(amount*bps+9999)//10000)
    return {"fee_base_units":fee,"net_base_units":amount-fee,
            "schedule_epoch":schedule["epoch"]}
