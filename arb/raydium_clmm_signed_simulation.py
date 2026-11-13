"""Verify a signed Raydium CLMM swap_v2 simulation against SPL account deltas.

Simulation only: this module never broadcasts or signs a transaction. Caller
must provide a fully signed transaction and authenticated pre-state balances.
"""
import base64
from arb.rpc import call
from arb.raydium_clmm import PROGRAM
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
from arb.pumpswap_local_simulation import local_rpc_only


def simulate_signed(rpc,wire,input_address,output_address,input_mint,output_mint,
                    before_input,before_output,max_spend,min_receive):
    local_rpc_only(rpc)
    if (not isinstance(wire,bytes) or not wire or
            any(not isinstance(x,str) or not x for x in
                (input_address,output_address,input_mint,output_mint)) or
            input_address==output_address or input_mint==output_mint or
            any(type(x)is not int for x in
                (before_input,before_output,max_spend,min_receive)) or
            not 0<max_spend<1<<64 or not 0<=min_receive<1<<64 or
            not max_spend<=before_input<1<<64 or
            not 0<=before_output<1<<64):
        raise ValueError("invalid CLMM signed simulation inputs")
    value=call(rpc,"simulateTransaction",[
        base64.b64encode(wire).decode("ascii"),
        {"encoding":"base64","sigVerify":True,"replaceRecentBlockhash":False,
         "accounts":{"encoding":"base64",
                     "addresses":[input_address,output_address]}}])["value"]
    if value.get("err") is not None:
        raise ValueError("CLMM swap simulation failed: "+str(value["err"]))
    logs=value.get("logs")
    if (not isinstance(logs,list) or
            not any("Program "+PROGRAM+" invoke" in x for x in logs)):
        raise ValueError("CLMM program invocation missing")
    accounts=value.get("accounts")
    if not isinstance(accounts,list) or len(accounts)!=2:
        raise ValueError("missing CLMM simulated post-token balances")
    amounts=[]
    for account,mint in zip(accounts,(input_mint,output_mint)):
        if not isinstance(account,dict) or account.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("unsupported simulated token account owner")
        data=account.get("data")
        if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
            raise ValueError("missing simulated token account data")
        state=decode_token_account(base64.b64decode(data[0],validate=True))
        if state["mint"]!=mint:
            raise ValueError("CLMM simulated token mint mismatch")
        amounts.append(state["amount_base_units"])
    spent=before_input-amounts[0]
    received=amounts[1]-before_output
    if not 0<spent<=max_spend or not received>=min_receive or received<=0:
        raise ValueError("CLMM simulation post-balance economics invalid")
    units=value.get("unitsConsumed")
    if type(units)is not int or units<=0:
        raise ValueError("CLMM simulation missing compute usage")
    return {"status":"SIGNED_CLMM_SWAP_SIMULATED","simulation_verified":True,
            "spent_base_units":spent,"received_base_units":received,
            "units_consumed":units,"actionable":False,
            "profitable_arbitrage_verified":False,"mainnet_broadcast":False}
