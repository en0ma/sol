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
    if len(raw)<166 or raw[108]!=1:
        raise ValueError("uninitialized or truncated Token-2022 account")
    types=extension_types(raw,ACCOUNT_TYPE_ACCOUNT)
    return {"mint":b58(raw[:32]),"authority":b58(raw[32:64]),
            "amount_base_units":int.from_bytes(raw[64:72],"little"),
            "state":raw[108],"token_program":"token_2022",
            "extension_types":types,"execution_eligible":False}
