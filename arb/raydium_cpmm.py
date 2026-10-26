"""Raydium CPMM (cp-swap) account decoder and bounded SOL/USDC discovery.

On-chain RPC ONLY. No Raydium HTTP API, no broad unfiltered program scan,
no assertion that a program account is a tradable pool without vault checks.
Reference: raydium-io/raydium-cp-swap PoolState packed Anchor layout.
"""
import argparse
import base64
import hashlib
import json
import os
from arb.rpc import call
from arb.orca_whirlpool import SOL,USDC,b58
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
PROGRAM="CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"
SIZE=637
DISC=hashlib.sha256(b"account:PoolState").digest()[:8]

def decode(raw):
    if len(raw)!=SIZE or raw[:8]!=DISC:
        raise ValueError("invalid Raydium CPMM PoolState discriminator or size")
    keys=[b58(raw[8+i*32:40+i*32]) for i in range(10)]
    if len(set(keys[2:7]))!=5:
        raise ValueError("duplicate token accounts or mints")
    if raw[389] not in (0,1,2) or raw[390] not in (0,1):
        raise ValueError("invalid on-chain CPMM creator fee mode or flag")
    return {"amm_config":keys[0],"creator":keys[1],
        "token_0_vault":keys[2],"token_1_vault":keys[3],
        "lp_mint":keys[4],"token_0_mint":keys[5],"token_1_mint":keys[6],
        "token_0_program":keys[7],"token_1_program":keys[8],
        "observation":keys[9],
        "auth_bump":raw[328],"status":raw[329],
        "mint_0_decimals":raw[331],"mint_1_decimals":raw[332],
        "swap_enabled":not bool(raw[329]&4),
        "creator_fee_on":raw[389],
        "enable_creator_fee":bool(raw[390])}

def candidates(rpc,max_candidates=12):
    if type(max_candidates)!=int or not 1<=max_candidates<=50:
        raise ValueError("candidate limit must be 1-50")
    output={}
    for a,b in ((SOL,USDC),(USDC,SOL)):
        filters=[{"dataSize":SIZE},{"memcmp":{"offset":168,"bytes":a}},
                 {"memcmp":{"offset":200,"bytes":b}}]
        found=call(rpc,"getProgramAccounts",[PROGRAM,{
            "encoding":"base64","commitment":"confirmed","filters":filters}],timeout=35)
        if not isinstance(found,list) or len(found)>max_candidates:
            raise ValueError("too many CPMM candidates; fail closed")
        for item in found:
            acc=item["account"]
            if acc["owner"]!=PROGRAM or acc.get("executable"):
                raise ValueError("wrong CPMM account owner")
            encoded=acc["data"]
            state=decode(base64.b64decode(encoded[0],validate=True))
            if (state["token_0_mint"],state["token_1_mint"])!=(a,b):
                raise ValueError("filtered candidate mint mismatch")
            output[item["pubkey"]]=state
    return output

def verify_vaults(rpc,pool_address,state,*,expected_mints=(SOL,USDC)):
    """Verify classic-SPL CPMM pool and reserves.

    Existing WSOL/USDC callers retain the exact-pair default. A graph verifier
    may pass expected_mints=None and independently match the route's mint hints.
    """
    actual = (state["token_0_mint"], state["token_1_mint"])
    if len(set(actual)) != 2:
        raise ValueError("identical CPMM token mints")
    if expected_mints is not None and set(actual) != set(expected_mints):
        raise ValueError("unexpected CPMM token pair")
    if not state["swap_enabled"]:
        raise ValueError("CPMM swaps disabled")
    if state["token_0_program"]!=TOKEN_PROGRAM or state["token_1_program"]!=TOKEN_PROGRAM:
        raise ValueError("Token-2022 not yet supported")
    addresses=[pool_address,state["token_0_vault"],state["token_1_vault"]]
    res=call(rpc,"getMultipleAccounts",[addresses,{
         "encoding":"base64","commitment":"confirmed"}])
    values=res.get("value")
    if not isinstance(values,list) or len(values)!=3:
        raise ValueError("missing CPMM accounts")
    pool=values[0]
    if not pool or pool["owner"]!=PROGRAM or decode(base64.b64decode(
        pool["data"][0],validate=True))!=state:
        raise ValueError("CPMM pool mutated or wrong owner")
    vaults=[]
    for i in (0,1):
        v=values[i+1]
        if not v or v["owner"]!=TOKEN_PROGRAM:
            raise ValueError("missing SPL vault")
        dec=decode_token_account(base64.b64decode(v["data"][0],validate=True))
        if dec["mint"]!=state[f"token_{i}_mint"] or dec["amount_base_units"]<=0:
            raise ValueError("CPMM vault mint mismatch or empty")
        vaults.append(dec)
    if vaults[0]["authority"]!=vaults[1]["authority"]:
        raise ValueError("vault authority mismatch")
    return {"pool":pool_address,"slot":res.get("context",{}).get("slot"),
        "verified":True,"reserves_base_units":[x["amount_base_units"] for x in vaults],
        "program":PROGRAM,"swap_enabled":True,
        "swap_instruction_simulated":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--discover",action="store_true")
    p.add_argument("--manifest",default="arb/raydium_cpmm_pools.json")
    p.add_argument("--output")
    args=p.parse_args()
    rpc=os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899")
    with open(args.manifest) as f: entries=json.load(f)["pools"]
    reports=[]
    if args.discover:
        matches=candidates(rpc)
        for address,state in matches.items():
            try: reports.append(verify_vaults(rpc,address,state))
            except ValueError as exc:
                reports.append({"pool":address,"verified":False,"reason":str(exc)})
    for entry in entries:
        address=entry["address"]
        info=call(rpc,"getAccountInfo",[address,{"encoding":"base64"}])["value"]
        if not info or info["owner"]!=PROGRAM: raise ValueError("bad pinned CPMM pool")
        state=decode(base64.b64decode(info["data"][0],validate=True))
        reports.append(verify_vaults(rpc,address,state))
    output={"status":"PASS" if any(r.get("verified") for r in reports) else "NOT_CONFIGURED",
            "venue":"Raydium CPMM","pools":reports,"cross_venue_simulated":False}
    if args.output:
        with open(args.output,"w") as f:json.dump(output,f,indent=2)
    print(json.dumps(output,indent=2))
    return 0 if output["status"]=="PASS" else 2

if __name__=="__main__":
    raise SystemExit(main())
