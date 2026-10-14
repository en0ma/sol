"""Bounded on-chain DEX pool discovery and graph building; no DEX HTTP APIs.

Searches exact curated mint pairs via getProgramAccounts with size/offset
memcmp filters, verifies returned owners and account data, then reads vault
balances before admitting pools to the candidate graph. Read-only.
"""
import argparse,base64,json,os
from itertools import combinations
from arb.rpc import call
from arb.orca_whirlpool import PROGRAM as ORCA,SIZE as ORCA_SIZE,decode as decode_orca,SOL,USDC
from arb.raydium_cpmm import PROGRAM as RAY, SIZE as RAY_SIZE,decode as decode_ray
from arb.raydium_clmm import PROGRAM as CLMM,SIZE as CLMM_SIZE,decode as decode_clmm,verify as verify_clmm
from arb.whirlpool_snapshot import snapshot
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account

USDT="Es9vMFrzaCER9UtuaxKVHAn4i98TpxHcv2DgsLg8n4v"
JUP="JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN"
MINTS={"WSOL":SOL,"USDC":USDC,"USDT":USDT,"JUP":JUP}
VENUES={"orca":(ORCA,ORCA_SIZE,101,181,decode_orca),
        "raydium_cpmm":(RAY,RAY_SIZE,168,200,decode_ray),
        "raydium_clmm":(CLMM,CLMM_SIZE,73,105,decode_clmm)}

def search_pair(rpc,venue,mint_a,mint_b,limit=8):
    if venue not in VENUES or mint_a==mint_b:raise ValueError("invalid search")
    if type(limit)is not int or not 1<=limit<=32:raise ValueError("invalid search limit")
    program,size,offset_a,offset_b,decode=VENUES[venue]
    found={}
    for a,b in ((mint_a,mint_b),(mint_b,mint_a)):
        config={"encoding":"base64","commitment":"confirmed",
           "filters":[{"dataSize":size},{"memcmp":{"offset":offset_a,"bytes":a}},
                      {"memcmp":{"offset":offset_b,"bytes":b}}]}
        response=call(rpc,"getProgramAccounts",[program,config],timeout=45)
        if not isinstance(response,list):
            raise ValueError("unexpected getProgramAccounts result")
        # Fail closed: no silent trimming of incomplete discovery results.
        if len(response)>limit:raise ValueError("pool search exceeded per-order limit")
        for entry in response:
            if entry["account"].get("owner")!=program or entry["account"].get("executable"):
                raise ValueError("wrong program owner")
            raw=base64.b64decode(entry["account"]["data"][0],validate=True)
            decoded=decode(raw)
            pair=(decoded["token_mint_a"],decoded["token_mint_b"]) if venue=="orca" else (
                decoded["token_mint_0"],decoded["token_mint_1"]) if venue=="raydium_clmm" else (
                decoded["token_0_mint"],decoded["token_1_mint"])
            if pair!=(a,b):raise ValueError("mint filter mismatch")
            found[entry["pubkey"]]=decoded
    return found

def verify(rpc,venue,address,state):
    if venue=="raydium_clmm":
        return verify_clmm(rpc,address,state)
    if venue=="orca":
        s=snapshot(rpc,address)
        if s["pool"]!=state:raise ValueError("Orca account changed while validating")
        amounts=[s["vault_a"]["amount_base_units"],s["vault_b"]["amount_base_units"]]
        pair=(state["token_mint_a"],state["token_mint_b"])
        slot=s["slot"]
    else:
        if not state["swap_enabled"]:raise ValueError("Raydium swaps disabled")
        if state["token_0_program"]!=TOKEN_PROGRAM or state["token_1_program"]!=TOKEN_PROGRAM:
            raise ValueError("unsupported token program")
        keys=[address,state["token_0_vault"],state["token_1_vault"]]
        resp=call(rpc,"getMultipleAccounts",[keys,{"encoding":"base64","commitment":"confirmed"}])
        values=resp.get("value")
        if not isinstance(values,list) or len(values)!=3:raise ValueError("missing Raydium accounts")
        pool=values[0]
        if not pool or pool.get("owner")!=RAY or decode_ray(base64.b64decode(pool["data"][0],validate=True))!=state:
            raise ValueError("Raydium state mutated")
        amounts=[]
        for i in (0,1):
            vault=values[i+1]
            if not vault or vault.get("owner")!=TOKEN_PROGRAM:raise ValueError("invalid vault owner")
            decoded=decode_token_account(base64.b64decode(vault["data"][0],validate=True))
            if decoded["mint"]!=state[f"token_{i}_mint"]:raise ValueError("vault mint mismatch")
            amounts.append(decoded["amount_base_units"])
        pair=(state["token_0_mint"],state["token_1_mint"])
        slot=resp.get("context",{}).get("slot")
    if min(amounts)<=0:raise ValueError("empty reserves")
    return {"venue":venue,"address":address,"mints":list(pair),"slot":slot,
            "vault_base_units":amounts,"swap_simulated":False}

def discover(rpc,pairs,limit=8):
    results=[];errors=[]
    for a,b in pairs:
        for venue in VENUES:
            try:
                found=search_pair(rpc,venue,a,b,limit)
                for address,state in found.items():
                    try:results.append(verify(rpc,venue,address,state))
                    except ValueError as exc:errors.append({"venue":venue,"address":address,"error":str(exc)})
            except Exception as exc:
                errors.append({"venue":venue,"pair":[a,b],"error":type(exc).__name__+": "+str(exc)[:250]})
    by_pair={}
    for pool in results:
        key=tuple(sorted(pool["mints"]))
        by_pair.setdefault(key,set()).add(pool["venue"])
    shared=[{"mints":list(k),"venues":sorted(v)} for k,v in by_pair.items() if len(v)>1]
    return {"status":"COMPLETE" if not errors else "PARTIAL",
            "pools_verified":len(results),"shared_pairs":shared,
            "pools":results,"errors":errors,
            "route_simulated":False,"profitable_opportunities_confirmed":0}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--pairs",default="WSOL/USDT,WSOL/JUP,USDC/USDT")
    p.add_argument("--output",default=os.environ.get("DEX_DISCOVERY_REPORT",""))
    p.add_argument("--limit",type=int,default=8)
    args=p.parse_args()
    pairs=[]
    for item in args.pairs.split(","):
        a,b=item.strip().split("/")
        if a not in MINTS or b not in MINTS:raise ValueError("mint not on curated allowlist")
        pairs.append((MINTS[a],MINTS[b]))
    if len(pairs)>6:raise ValueError("pair budget exceeded")
    report=discover(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),pairs,args.limit)
    print(json.dumps(report,indent=2))
    if args.output:
        with open(args.output,"w") as f:json.dump(report,f,indent=2)
    # No pools is a legitimate observation; incomplete RPC reads are not.
    return 0 if report["status"]=="COMPLETE" else 2
if __name__=="__main__":raise SystemExit(main())
