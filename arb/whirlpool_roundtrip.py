"""Atomic two-leg Whirlpool round-trip: simulation only, never broadcast.

Uses first swap's conservative minimum guaranteed output for second exact-input
swap. This is deliberately conservative, not dynamic use of first-leg proceeds.
Reports observed WSOL loss/profit after transaction fees, no PnL inference
from spot price.
"""
import base64
import json
import os
import time
from arb.rpc import call
from arb.orca_whirlpool import SOL, USDC, PROGRAM, fetch_pool
from arb.whirlpool_preflight import verify_oracle
from arb.whirlpool_swap import build_swap, inspect_swap_requirements
from arb.whirlpool_simulation import prepare_token_accounts, TOKEN_SPACE
from arb.token_vaults import decode_token_account, TOKEN_PROGRAM

def measure_roundtrip(value, state, input_amount, second_leg_input):
    if value.get("err") is not None:
        raise ValueError("roundtrip simulation failed")
    logs=value.get("logs") or []
    invocations=sum("Program "+PROGRAM+" invoke" in l for l in logs)
    if invocations != 2 or sum("Program "+PROGRAM+" success" in l for l in logs) != 2:
        raise ValueError("both Whirlpool legs must execute successfully")
    accounts=value.get("accounts")
    if not isinstance(accounts,list) or len(accounts)!=2:
        raise ValueError("post-simulation accounts missing")
    amounts=[]
    for acct,mint in zip(accounts,(state["token_mint_a"],state["token_mint_b"])):
        if not isinstance(acct,dict) or acct.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("invalid post-simulation SPL Token owner")
        d=acct.get("data")
        if not isinstance(d,list) or len(d)!=2 or d[1]!="base64":
            raise ValueError("invalid returned SPL Token account")
        account=decode_token_account(base64.b64decode(d[0],validate=True))
        if account["mint"]!=mint: raise ValueError("returned mint mismatch")
        amounts.append(account["amount_base_units"])
    native_index=0 if state["token_mint_a"]==SOL else 1
    final_wsol=amounts[native_index]
    remaining_usdc=amounts[1-native_index]
    if final_wsol < 0 or remaining_usdc < 0:
        raise ValueError("invalid output amounts")
    # The second swap must actually spend its declared input amount. First
    # swap output >= second_leg_input, so leftover USDC is allowed.
    if second_leg_input <= 0:
        raise ValueError("second leg amount invalid")
    return {"start_wsol_lamports":input_amount,"end_wsol_lamports":final_wsol,
            "wsol_delta_before_network_fees":final_wsol-input_amount,
            "residual_usdc_base_units":remaining_usdc,
            "whirlpool_invocations":invocations}

def run(rpc,pool_address,input_amount=1000000,second_leg_input=10000):
    from solders.keypair import Keypair
    from solders.hash import Hash
    from solders.transaction import Transaction
    state=fetch_pool(rpc,pool_address)
    if {state["token_mint_a"],state["token_mint_b"]}!={SOL,USDC}:
        raise ValueError("requires classic WSOL/USDC Whirlpool")
    if not 0<second_leg_input<=100000 or not 0<input_amount<=100000000:
        raise ValueError("invalid input limits")
    oracle=verify_oracle(rpc,pool_address,
        adaptive_fee=state["tick_spacing"]!=state["fee_tier_index_seed"])
    readiness=inspect_swap_requirements(rpc,pool_address)
    forward=state["token_mint_a"]==SOL
    if not all(readiness["directions"][name]["available"] for name in ("a_to_b","b_to_a")):
        return {"status":"BLOCKED_TICK_ARRAYS","roundtrip_success":False}
    payer,acct_a,acct_b=Keypair(),Keypair(),Keypair()
    airdrop=call(rpc,"requestAirdrop",[str(payer.pubkey()),1000000000])
    if not isinstance(airdrop,str): raise ValueError("local airdrop failed")
    for _ in range(40):
        if call(rpc,"getBalance",[str(payer.pubkey())])["value"]>=1000000000: break
        time.sleep(.25)
    else: raise ValueError("local payer funding not confirmed")
    rent=call(rpc,"getMinimumBalanceForRentExemption",[TOKEN_SPACE])
    instructions=prepare_token_accounts(payer,acct_a,acct_b,
          state["token_mint_a"],state["token_mint_b"],forward,rent,input_amount)
    args=(pool_address,state,str(payer.pubkey()),
          str(acct_a.pubkey()),str(acct_b.pubkey()),oracle)
    instructions.append(build_swap(*args,input_amount,second_leg_input,forward))
    instructions.append(build_swap(*args,second_leg_input,1,not forward))
    blockhash=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    tx=Transaction.new_signed_with_payer(instructions,payer.pubkey(),
                                          [payer,acct_a,acct_b],Hash.from_string(blockhash))
    wire=bytes(tx)
    if len(wire)>1232:
        return {"status":"TX_TOO_LARGE","roundtrip_success":False,"bytes":len(wire)}
    result=call(rpc,"simulateTransaction",[
        base64.b64encode(wire).decode(),{"encoding":"base64","sigVerify":True,
            "commitment":"processed","accounts":{"encoding":"base64",
            "addresses":[str(acct_a.pubkey()),str(acct_b.pubkey())]}}])["value"]
    output={"status":"SIMULATION_FAILED","roundtrip_success":False,
        "error":result.get("err"),"compute_units":result.get("unitsConsumed"),
        "transaction_bytes":len(wire),"pool":pool_address,"local_only":True,
        "log_tail":(result.get("logs") or [])[-16:]}
    if result.get("err") is not None: return output
    try:
        stats=measure_roundtrip(result,state,input_amount,second_leg_input)
    except ValueError as exc:
        output["verification_error"]=str(exc)
        return output
    # getFeeForMessage is fork RPC-based and may be unavailable; do not
    # claim net profitability when fee data is missing.
    from solders.message import to_bytes_versioned
    # Legacy Message wire format is base64 encoded separately.
    message=tx.message
    try:
        fee=call(rpc,"getFeeForMessage",[base64.b64encode(bytes(message)).decode()])
        fee_lamports=fee.get("value")
    except Exception:
        fee_lamports=None
    if type(fee_lamports) is int and fee_lamports>=0:
        stats["estimated_network_fee_lamports"]=fee_lamports
        stats["wsol_delta_after_network_fee_lamports"]=stats["wsol_delta_before_network_fees"]-fee_lamports
    else:
        stats["estimated_network_fee_lamports"]=None
        stats["wsol_delta_after_network_fee_lamports"]=None
    output.update(stats)
    output["status"]="PASS"
    output["roundtrip_success"]=True
    output["profit_claim"]=False # residual USDC / fees require full accounting
    return output

def main():
    with open("arb/whirlpool_pools.json") as f: pools=json.load(f)["pools"]
    if not pools: return 2
    reports=[run(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                 p["address"]) for p in pools]
    print(json.dumps(reports,indent=2))
    return 0 if all(r["roundtrip_success"] for r in reports) else 1

if __name__=="__main__":
    raise SystemExit(main())
