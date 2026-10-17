"""Read-only, same-slot Orca structural validation for mixed SPL / Token-2022 pools.

A structurally authenticated pool is NOT executable. Token-2022 mint and
account extensions, transfer fees, hooks, and quote account metas must be
handled separately before trading/simulation admission.
"""
import base64
from arb.rpc import call
from arb.orca_whirlpool import PROGRAM, decode, fetch_pool
from arb.token_vaults import TOKEN_PROGRAM
from arb.token2022_extensions import TOKEN_2022, account_observation, extension_types

def _raw(info,owner):
    if not isinstance(info,dict) or info.get("owner")!=owner or info.get("executable"):
        raise ValueError("missing account or owner mismatch")
    data=info.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("invalid base64 account payload")
    return base64.b64decode(data[0],validate=True)

def _mint(info):
    if not isinstance(info,dict) or info.get("owner") not in (TOKEN_PROGRAM,TOKEN_2022):
        raise ValueError("mint owner unsupported")
    owner=info["owner"]
    raw=_raw(info,owner)
    if len(raw)<82 or raw[45]!=1:
        raise ValueError("mint is truncated or uninitialized")
    if owner==TOKEN_PROGRAM:
        if len(raw)!=82:raise ValueError("classic mint has invalid size")
        extensions=[]
    elif len(raw)==82:
        extensions=[]
    else:
        if len(raw)<166 or any(raw[82:165]):
            raise ValueError("invalid Token-2022 mint padding")
        extensions=extension_types(raw,1)
    return {"owner":owner,"extension_types":extensions,
            "supply":int.from_bytes(raw[36:44],"little"),"decimals":raw[44]}

def snapshot(rpc,address):
    seed=fetch_pool(rpc,address)
    addrs=[address,seed["token_vault_a"],seed["token_vault_b"],
           seed["token_mint_a"],seed["token_mint_b"]]
    if len(set(addrs))!=5:raise ValueError("pool, vault and mint accounts overlap")
    response=call(rpc,"getMultipleAccounts",[addrs,{"encoding":"base64","commitment":"confirmed"}])
    slot=response.get("context",{}).get("slot")
    values=response.get("value")
    if not isinstance(slot,int) or not isinstance(values,list) or len(values)!=5:
        raise ValueError("missing synchronized pool/vault/mint snapshot")
    pool=decode(_raw(values[0],PROGRAM))
    if (pool["token_vault_a"]!=addrs[1] or pool["token_vault_b"]!=addrs[2] or
            pool["token_mint_a"]!=addrs[3] or pool["token_mint_b"]!=addrs[4]):
        raise ValueError("pool state changed before synchronized snapshot")
    mints=[_mint(values[3]),_mint(values[4])]
    vaults=[]
    for i in range(2):
        info=values[i+1]
        raw=_raw(info,mints[i]["owner"])
        obs=account_observation(info["owner"],raw)
        if obs["mint"]!=addrs[i+3] or obs["state"]!=1 or obs["amount_base_units"]<=0:
            raise ValueError("vault mint/state/amount invalid")
        vaults.append(obs)
    if vaults[0]["authority"]!=vaults[1]["authority"] or int(pool["liquidity"])<=0:
        raise ValueError("vault authorities differ or active liquidity zero")
    return {"venue":"orca","address":address,"slot":slot,
            "mints":[addrs[3],addrs[4]],"mint_accounts":mints,
            "vault_accounts":vaults,"structurally_verified":True,
            "effective_fee_verified":False,"executable_quote":False,
            "actionable":False,"simulation_verified":False,"broadcast":False}
