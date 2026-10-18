"""Read-only, same-slot Orca structural validation for mixed SPL / Token-2022 pools.

A structurally authenticated pool is NOT executable. Token-2022 mint and
account extensions, transfer fees, hooks, and quote account metas must be
handled separately before trading/simulation admission.
"""
import base64
from arb.rpc import call
from arb.orca_whirlpool import PROGRAM, decode, fetch_pool
from arb.token_vaults import TOKEN_PROGRAM
from arb.token2022_extensions import TOKEN_2022, account_observation, extension_types, transfer_fee_config, transfer_hook_program_id

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
    fee_config=transfer_fee_config(raw) if owner==TOKEN_2022 and 1 in extensions else None
    hook_id=transfer_hook_program_id(raw) if 14 in extensions else None
    return {"owner":owner,"extension_types":extensions,
            "transfer_hook_program_id":hook_id,
            "transfer_fee_config":fee_config,
            "supply":int.from_bytes(raw[36:44],"little"),"decimals":raw[44]}

# IDs from SPL Token-2022 ExtensionType; presence is NOT quote authorization.
EXTENSION_NAMES={1:"TRANSFER_FEE_CONFIG",3:"MINT_CLOSE_AUTHORITY",
    4:"CONFIDENTIAL_TRANSFER_MINT",6:"DEFAULT_ACCOUNT_STATE",
    9:"NON_TRANSFERABLE",10:"INTEREST_BEARING_CONFIG",
    12:"PERMANENT_DELEGATE",14:"TRANSFER_HOOK",
    16:"CONFIDENTIAL_TRANSFER_FEE_CONFIG",18:"METADATA_POINTER",
    19:"TOKEN_METADATA",25:"SCALED_UI_AMOUNT",26:"PAUSABLE"}
QUOTE_BLOCKING_EXTENSIONS={1,4,6,9,10,12,14,16,25,26}

def extension_risk(mint_accounts):
    if not isinstance(mint_accounts,list) or len(mint_accounts)!=2:
        raise ValueError("expected two mint observations")
    observed=sorted({kind for mint in mint_accounts
                     for kind in mint["extension_types"]})
    blocking=sorted({kind for kind in observed
                     if kind in QUOTE_BLOCKING_EXTENSIONS or kind not in EXTENSION_NAMES})
    return {"mint_extension_ids":observed,
            "mint_extension_names":[EXTENSION_NAMES.get(k,"UNKNOWN_"+str(k)) for k in observed],
            "requires_specialized_quote_support":bool(blocking),
            "blocking_extension_ids":blocking,
            "fee_mode_verified":False,"executable_quote":False}

def snapshot(rpc,address,*,min_context_slot=None,include_ticks=False):
    if min_context_slot is not None and (type(min_context_slot)is not int or min_context_slot<0):
        raise ValueError("invalid minimum context slot")
    seed=fetch_pool(rpc,address)
    addrs=[address,seed["token_vault_a"],seed["token_vault_b"],
           seed["token_mint_a"],seed["token_mint_b"]]
    if len(set(addrs))!=5:raise ValueError("pool, vault and mint accounts overlap")
    tick_starts=[]
    tick_keys=[]
    if include_ticks:
        from arb.whirlpool_ticks import candidate_starts,addresses
        tick_starts=candidate_starts(seed["tick_current_index"],seed["tick_spacing"])
        tick_keys=addresses(address,tick_starts)
        addrs+=tick_keys
    options={"encoding":"base64","commitment":"confirmed"}
    if min_context_slot is not None:
        options["minContextSlot"]=min_context_slot
    response=call(rpc,"getMultipleAccounts",[addrs,options])
    slot=response.get("context",{}).get("slot")
    values=response.get("value")
    if not isinstance(slot,int) or not isinstance(values,list) or len(values)!=len(addrs):
        raise ValueError("missing synchronized pool/vault/mint snapshot")
    if min_context_slot is not None and slot<min_context_slot:
        raise ValueError("RPC returned stale account snapshot despite minContextSlot")
    pool={"address":address,**decode(_raw(values[0],PROGRAM))}
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
    tick_arrays=None
    if include_ticks:
        from arb.whirlpool_ticks import (decode_fixed_ticks,decode_dynamic_ticks,
                                          FIXED_LEN,DISC,DYNAMIC_DISC)
        if (pool["tick_current_index"]!=seed["tick_current_index"] or
                pool["tick_spacing"]!=seed["tick_spacing"]):
            raise ValueError("pool tick index changed before synchronized snapshot")
        tick_arrays=[]
        for start,key,account in zip(tick_starts,tick_keys,values[5:]):
            entry={"start_tick":start,"address":key,"status":"MISSING"}
            if account is not None:
                raw=_raw(account,PROGRAM)
                if len(raw)==FIXED_LEN and raw[:8]==DISC:
                    entry["ticks"]=decode_fixed_ticks(raw,address,start,pool["tick_spacing"])
                    entry["status"]="FIXED_VALID"
                elif raw[:8]==DYNAMIC_DISC:
                    entry["ticks"]=decode_dynamic_ticks(raw,address,start,pool["tick_spacing"])
                    entry["status"]="FIXED_VALID"
                else:
                    entry["status"]="UNSUPPORTED_LAYOUT"
            tick_arrays.append(entry)
    risks=extension_risk(mints)
    return {"venue":"orca","address":address,"slot":slot,"pool":pool,
            "mints":[addrs[3],addrs[4]],"mint_accounts":mints,
            "vault_accounts":vaults,"tick_arrays":tick_arrays,"extension_risk":risks,"structurally_verified":True,
            "effective_fee_verified":False,"executable_quote":False,
            "actionable":False,"simulation_verified":False,"broadcast":False}

def main():
    import argparse,json,os
    from pathlib import Path
    p=argparse.ArgumentParser()
    p.add_argument("--cohort",default="arb/orca_token2022_audit_cohort.json")
    p.add_argument("--output",required=True)
    p.add_argument("--limit",type=int,default=15)
    args=p.parse_args()
    if type(args.limit) is not int or not 1<=args.limit<=50:
        raise ValueError("invalid structural audit limit")
    rows=json.loads(Path(args.cohort).read_text())["addresses"]
    if not isinstance(rows,list) or len(rows)>50 or len(set(rows))!=len(rows):
        raise ValueError("invalid candidate cohort")
    rpc=os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899")
    observations=[]
    for address in rows[:args.limit]:
        try:
            item=snapshot(rpc,address)
            observations.append({"address":address,"structurally_verified":True,
                                 "slot":item["slot"],"mint_accounts":item["mint_accounts"],
                                 "vault_accounts":item["vault_accounts"],"extension_risk":item["extension_risk"],
                                 "actionable":False})
        except Exception as exc:
            observations.append({"address":address,"structurally_verified":False,
                                 "error":type(exc).__name__+": "+str(exc)[:180],
                                 "actionable":False})
    result={"cohort_size":len(rows),"checked":len(observations),
            "structurally_verified_count":sum(x["structurally_verified"] for x in observations),
            "observations":observations,"actionable":False,"mainnet_broadcast":False}
    Path(args.output).write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!="observations"},indent=2))

if __name__=="__main__":
    main()
