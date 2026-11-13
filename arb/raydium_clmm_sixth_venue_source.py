"""Sixth venue: bounded, read-only Raydium CLMM source authentication.

This reuses the existing Raydium CLMM PoolState and SwapV2 adapter.
A synchronized on-chain snapshot is necessary, not proof of integer
tick-crossing prices, signed swaps or registry eligibility.
"""
import argparse,base64,hashlib,json
from pathlib import Path
from arb.rpc import call
from arb.raydium_clmm import PROGRAM,decode
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account

SAFE={"actionable":False,"broadcast":False,"native_pricing_verified":False,
      "signed_parity_verified":False,"registry_admission_approved":False}

def _bytes(account,owner):
    if not isinstance(account,dict) or account.get("owner")!=owner or account.get("executable") is not False:
        raise ValueError("CLMM account owner/executable mismatch")
    item=account.get("data")
    if not isinstance(item,list) or len(item)!=2 or item[1]!="base64":
        raise ValueError("CLMM account bytes unavailable")
    return base64.b64decode(item[0],validate=True)

def capture_pool(rpc,pool,expected_mints):
    pre=call(rpc,"getAccountInfo",[pool,{"encoding":"base64","commitment":"confirmed"}])
    state=decode(_bytes(pre.get("value"),PROGRAM))
    mints=[state["token_mint_0"],state["token_mint_1"]]
    if expected_mints is not None and (not isinstance(expected_mints,list) or set(mints)!=set(expected_mints) or len(expected_mints)!=2):
        raise ValueError("Raydium CLMM tracked pool mint identity disagrees")
    if state["liquidity"]<=0 or state["swap_status_bits"] & (1<<4):
        raise ValueError("Raydium CLMM pool disabled or empty")
    keys=[pool,state["token_vault_0"],state["token_vault_1"],state["amm_config"],
          state["observation_key"],*mints]
    res=call(rpc,"getMultipleAccounts",[keys,{"encoding":"base64","commitment":"confirmed"}])
    slot=res.get("context",{}).get("slot")
    accounts=res.get("value")
    if type(slot) is not int or slot<0 or not isinstance(accounts,list) or len(accounts)!=len(keys):
        raise ValueError("Raydium CLMM unsynchronized source snapshot")
    if decode(_bytes(accounts[0],PROGRAM))!=state:
        raise ValueError("Raydium CLMM pool drifted during capture")
    tokens=[decode_token_account(_bytes(a,TOKEN_PROGRAM)) for a in accounts[1:3]]
    if ([t["mint"] for t in tokens]!=mints or
        tokens[0]["authority"]!=tokens[1]["authority"] or
        min(t["amount_base_units"] for t in tokens)<=0):
        raise ValueError("Raydium CLMM SPL vault mint/authority/balance invalid")
    for a in accounts[3:5]:
        _bytes(a,PROGRAM)
    for a in accounts[5:7]:
        raw=_bytes(a,TOKEN_PROGRAM)
        if len(raw)!=82 or raw[45]!=1:
            raise ValueError("Raydium CLMM unsupported mint layout")
    records=[{"address":key,"owner":a["owner"],"lamports":a["lamports"],
              "account_base64":a["data"][0]} for key,a in zip(keys,accounts)]
    digest=hashlib.sha256(json.dumps({"slot":slot,"accounts":records},
         sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return {"venue":"raydium_clmm","address":pool,"mints":mints,
        "source_slot":slot,"source_sha256":digest,"source_accounts":records,
        "tick_current":state["tick_current"],"tick_spacing":state["tick_spacing"],
        "sqrt_price_x64":str(state["sqrt_price_x64"]),
        "status":"CLMM_AUTHENTICATED_SOURCE_NOT_SIGNED",**SAFE}

def capture(rpc,registry,*,count=1):
    if type(count) is not int or not 1<=count<=3 or not isinstance(registry,dict) or not isinstance(registry.get("pools"),list):
        raise ValueError("bounded Raydium CLMM registry required")
    candidates=[r for r in registry["pools"] if isinstance(r,dict) and r.get("venue")=="raydium_clmm"]
    accepted=[];rejected=[]
    for row in candidates:
        if len(accepted)==count:break
        try:accepted.append(capture_pool(rpc,row["address"],row.get("mints")))
        except (ValueError,KeyError,TypeError,OSError,RuntimeError) as exc:
            rejected.append({"address":row.get("address"),"reason":str(exc)[:200]})
    return {"venue":"raydium_clmm","status":"SIXTH_VENUE_SOURCE_RESEARCH",
        "requested":count,"authenticated":len(accepted),"pools":accepted,
        "rejected":rejected,**SAFE}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rpc",required=True)
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--count",type=int,default=1)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=capture(a.rpc,json.loads(Path(a.registry).read_text()),count=a.count)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"authenticated":result["authenticated"],"requested":a.count,
                      "status":result["status"]}))
    if result["authenticated"]!=a.count:raise SystemExit("CLMM sixth-venue source authentication incomplete")
if __name__=="__main__":main()
