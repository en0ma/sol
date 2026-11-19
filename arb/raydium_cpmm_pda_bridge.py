"""Read-only Raydium CPMM pool PDA bridge discovery without getProgramAccounts.

Raydium cp-swap initialize.rs permits both deterministic pool-state PDAs
(seeds: b"pool", amm_config, token_0_mint, token_1_mint) AND arbitrary
signer-created pool addresses. This method discovers the PDA subset only.

Every configuration is extracted from source-owned CPMM pool-state accounts.
Every occupied derived pool is re-decoded and independently vault-verified
through the same source-backed local fork. Nothing is signed or broadcast.
"""
import base64
from arb.pumpswap_local_simulation import local_rpc_only
from arb.raydium_cpmm import PROGRAM,decode
from arb.onchain_pool_discovery import verify
from arb.rpc import call

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def source_config_addresses(rpc,entries,*,maximum_sources=24,call_fn=None):
    """Read source-owned CPMM state to collect AMM configuration addresses."""
    if type(maximum_sources)is not int or not 1<=maximum_sources<=48:
        raise ValueError("invalid config source budget")
    addresses=[e["address"] for e in entries if e.get("venue")=="raydium_cpmm"][:maximum_sources]
    if not addresses:
        return []
    fetch=call_fn or call
    response=fetch(rpc,"getMultipleAccounts",[addresses,
        {"encoding":"base64","commitment":"confirmed"}])
    values=response.get("value") if isinstance(response,dict) else None
    if not isinstance(values,list) or len(values)!=len(addresses):
        raise ValueError("missing source CPMM configuration snapshot")
    configs=set()
    for entry,account in zip(addresses,values):
        if not account or account.get("owner")!=PROGRAM or account.get("executable") is not False:
            continue
        try:
            state=decode(base64.b64decode(account["data"][0],validate=True))
            if state.get("amm_config"):
                configs.add(state["amm_config"])
        except (ValueError,TypeError,KeyError):
            continue
    return sorted(configs)


def discover(rpc,entries,pairs,*,maximum_pairs=24,maximum_configs=8,
             call_fn=None,verify_fn=None,config_fn=None):
    """Probe bounded deterministic CPMM PDA candidates and source verify."""
    from solders.pubkey import Pubkey
    local_rpc_only(rpc)
    if (not isinstance(entries,list) or not isinstance(pairs,list)
            or type(maximum_pairs)is not int or not 1<=maximum_pairs<=48
            or type(maximum_configs)is not int or not 1<=maximum_configs<=16):
        raise ValueError("invalid bounded CPMM PDA discovery inputs")
    existing={(e["venue"],e["address"]) for e in entries}
    unique=[]
    seen=set()
    for p in pairs:
        if (not isinstance(p,(list,tuple)) or len(p)!=2
                or not all(isinstance(m,str) and m for m in p)
                or p[0]==p[1]):
            raise ValueError("invalid CPMM pool pair")
        canonical=tuple(sorted(p))
        if canonical not in seen:
            unique.append(canonical)
            seen.add(canonical)
        if len(unique)>=maximum_pairs:
            break
    source_configs=config_fn(rpc,entries) if config_fn else source_config_addresses(
        rpc,entries,call_fn=call_fn)
    if (not isinstance(source_configs,list) or len(source_configs)>maximum_configs
            or len(source_configs)!=len(set(source_configs))):
        raise ValueError("CPMM source configuration bound exceeded")
    program=Pubkey.from_string(PROGRAM)
    pdas={}
    for config in source_configs:
        config_key=Pubkey.from_string(config)
        for pair in unique:
            a,b=sorted((Pubkey.from_string(pair[0]),Pubkey.from_string(pair[1])),
                       key=bytes)
            key=str(Pubkey.find_program_address(
                [b"pool",bytes(config_key),bytes(a),bytes(b)],program)[0])
            pdas[key]=pair
    fetch=call_fn or call
    verify_pool=verify_fn or verify
    selected={}
    errors=[]
    keys=list(pdas)
    for start in range(0,len(keys),100):
        group=keys[start:start+100]
        result=fetch(rpc,"getMultipleAccounts",[group,
            {"encoding":"base64","commitment":"confirmed"}])
        accounts=result.get("value") if isinstance(result,dict) else None
        if not isinstance(accounts,list) or len(accounts)!=len(group):
            raise ValueError("missing derived CPMM source snapshot")
        for address,account in zip(group,accounts):
            if account is None:
                continue
            try:
                if account.get("owner")!=PROGRAM or account.get("executable") is not False:
                    raise ValueError("CPMM derived account owner invalid")
                state=decode(base64.b64decode(account["data"][0],validate=True))
                if (tuple(sorted((state["token_0_mint"],state["token_1_mint"])))
                        !=pdas[address]):
                    raise ValueError("CPMM derived pool mint mismatch")
                source=verify_pool(rpc,"raydium_cpmm",address,state)
                if (not isinstance(source,dict) or
                        source.get("venue")!="raydium_cpmm" or
                        source.get("address")!=address or
                        type(source.get("slot")) is not int or
                        source["slot"]<0 or
                        tuple(sorted(source.get("mints",[])))!=pdas[address] or
                        source.get("swap_simulated") is not False):
                    raise ValueError("CPMM source verification mismatch")
                if ("raydium_cpmm",address) not in existing:
                    selected[address]={"venue":"raydium_cpmm",
                        "address":address,"mints":source["mints"],
                        "source_verified_slot":source["slot"],
                        "source_verified_only":True}
            except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
                # Avoid leaking credentials embedded in RPC exception text.
                errors.append({"address":address,"error":"SOURCE_CPMM_REAUTH_FAILED",
                               "exception_class":type(exc).__name__})
    return {"status":"READ_ONLY_RAYDIUM_CPMM_PDA_BRIDGE_DISCOVERY",
            "search_scope":"PDA_POOLS_ONLY_ARBITRARY_SIGNER_POOLS_NOT_SEARCHED",
            "source_config_count":len(source_configs),
            "pairs_searched":len(unique),"candidate_pdas_checked":len(keys),
            "source_verified_new_pools":list(selected.values()),
            "verified_new_pool_count":len(selected),
            "errors":errors,"source_authenticated":True,
            "signed_simulation_verified":False,**SAFE}
