"""Fork-only Whirlpool swap preflight using real on-chain pool/oracle/tick arrays.

Creates and signs a legacy swap transaction with an ephemeral signer, then
calls simulateTransaction on Surfpool only. Does not broadcast, fund token
accounts, or claim a successful swap. Missing user token accounts are explicit.
"""
import base64
import hashlib
import json
import os
from arb.rpc import call
from arb.orca_whirlpool import PROGRAM, fetch_pool
from arb.whirlpool_swap import build_swap, inspect_swap_requirements

def oracle_address(pool_address):
    key=Pubkey.from_string(pool_address)
    program=Pubkey.from_string(PROGRAM)
    return str(Pubkey.find_program_address([b"oracle",bytes(key)],program)[0])

def verify_oracle(rpc,pool_address, adaptive_fee=False):
    pubkey=oracle_address(pool_address)
    response=call(rpc,"getAccountInfo",[pubkey,{"encoding":"base64","commitment":"confirmed"}])
    info=response.get("value")
    if not info:
        if adaptive_fee:
            raise ValueError("Adaptive-fee Whirlpool oracle missing")
        # Anchor UncheckedAccount permits an uninitialized PDA.
        # Orca's legacy swap does not read its Oracle on non-adaptive pools.
        return pubkey
    if info.get("owner")!=PROGRAM or info.get("executable"):
        raise ValueError("Orca oracle exists with unexpected owner")
    data=info.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("malformed oracle data")
    raw=base64.b64decode(data[0],validate=True)
    disc=hashlib.sha256(b"account:Oracle").digest()[:8]
    if len(raw)<8 or raw[:8]!=disc:
        raise ValueError("incorrect Oracle account discriminator")
    return pubkey

def preflight(rpc,pool_address,amount=1000,a_to_b=True):
    # Pool and oracle must be checked via forked on-chain accounts.
    state=fetch_pool(rpc,pool_address)
    try:
        oracle=verify_oracle(rpc,pool_address,
            adaptive_fee=state["tick_spacing"] != state["fee_tier_index_seed"])
    except ValueError as exc:
        return {"status":"BLOCKED_ORACLE","swap_success":False,
                "pool":pool_address,"reason":str(exc)}
    requirements=inspect_swap_requirements(rpc,pool_address)
    direction="a_to_b" if a_to_b else "b_to_a"
    if not requirements["directions"][direction]["available"]:
        return {"status":"BLOCKED_TICK_ARRAYS","swap_success":False,
                "pool":pool_address,"direction":direction,"oracle":oracle}
    from solders.keypair import Keypair
    from solders.hash import Hash
    from solders.transaction import Transaction
    signer=Keypair()
    # Deliberately nonexistent user token accounts. This is an instruction
    # execution preflight, not a successful asset transfer simulation.
    fake_a=str(Keypair().pubkey())
    fake_b=str(Keypair().pubkey())
    ix=build_swap(pool_address,state,str(signer.pubkey()),fake_a,fake_b,
                  oracle,amount,1,a_to_b)
    blockhash=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    tx=Transaction.new_signed_with_payer([ix],signer.pubkey(),
                                         [signer],Hash.from_string(blockhash))
    wire=base64.b64encode(bytes(tx)).decode()
    response=call(rpc,"simulateTransaction",[wire,{
        "encoding":"base64","sigVerify":True,"commitment":"processed"}])
    value=response.get("value")
    if not isinstance(value,dict):
        raise ValueError("missing simulation result")
    logs=value.get("logs") or []
    invoked=any("Program "+PROGRAM+" invoke" in line for line in logs)
    # Ephemeral signer lacks fee balance and token accounts. Successful
    # simulation would be suspicious and must not be counted as a swap.
    return {"status":"PREFLIGHT_ONLY","swap_success":False,"pool":pool_address,
            "direction":direction,"oracle":oracle,"program_invoked":invoked,
            "simulation_error":value.get("err"),
            "units_consumed":value.get("unitsConsumed"),
            "notes":"No funded user SPL token accounts; no token transfer verified"}

def main():
    import sys
    with open("arb/whirlpool_pools.json") as f: pools=json.load(f)["pools"]
    if not pools: return 2
    rpc=os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899")
    results=[preflight(rpc,p["address"]) for p in pools]
    print(json.dumps(results,indent=2))
    # An honest diagnostic stage: pass only if RPC returned meaningful
    # preflight results; never report a complete swap.
    return 0

if __name__=="__main__":
    raise SystemExit(main())
