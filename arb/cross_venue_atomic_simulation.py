"""Fail-closed signed, local-only cross-venue atomic simulation verifier.

The transaction must already be signed and contain both swaps. This module
never constructs, sends or broadcasts transactions. Verifies both program
invocations and the intermediate token account's final balance. Intermediate
tokens may be consumed within the transaction without changing the final
intermediate account balance; that is permitted only with caller-supplied
verified instruction ordering and explicit logs for both programs.
"""
import base64
from arb.pumpswap_local_simulation import local_rpc_only
from arb.rpc import call
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account

def verify_signed_atomic(rpc,signed_bytes,*,first_program,second_program,
                         input_account,intermediate_account,output_account,
                         input_mint,intermediate_mint,output_mint,
                         initial_input,initial_intermediate,initial_output,
                         max_input,minimum_output):
    local_rpc_only(rpc)
    if not isinstance(signed_bytes,bytes) or not signed_bytes or len(signed_bytes)>1232:
        raise ValueError("missing signed Solana transaction or packet limit exceeded")
    addresses=(input_account,intermediate_account,output_account)
    mints=(input_mint,intermediate_mint,output_mint)
    if len(set(addresses))!=3 or len(set(mints))!=3:
        raise ValueError("atomic path requires distinct input, intermediate and output accounts and mints")
    if any(not isinstance(x,str) or not x for x in (*addresses,*mints,first_program,second_program)):
        raise ValueError("missing atomic path address or program")
    if first_program==second_program:
        raise ValueError("cross-venue atomic path requires distinct programs")
    amounts=(initial_input,initial_intermediate,initial_output,max_input,minimum_output)
    if any(type(x)is not int or x<0 or x>=1<<64 for x in amounts) or max_input<=0 or minimum_output<=0:
        raise ValueError("invalid atomic simulation balance or slippage threshold")
    if initial_input<max_input:
        raise ValueError("insufficient initial input for authorized maximum")
    response=call(rpc,"simulateTransaction",[
        base64.b64encode(signed_bytes).decode(),
        {"encoding":"base64","sigVerify":True,"replaceRecentBlockhash":False,
         "accounts":{"encoding":"base64","addresses":list(addresses)}}])
    value=response.get("value")
    if not isinstance(value,dict) or value.get("err") is not None:
        raise ValueError("atomic transaction simulation failed")
    logs=value.get("logs")
    if not isinstance(logs,list):
        raise ValueError("missing atomic execution logs")
    # Explicit invocation and successful exit required for each venue program.
    for program in (first_program,second_program):
        if not any(line.startswith("Program "+program+" invoke [") for line in logs):
            raise ValueError("missing venue program invocation: "+program)
        if not any(line=="Program "+program+" success" for line in logs):
            raise ValueError("venue program success absent: "+program)
    post=value.get("accounts")
    if not isinstance(post,list) or len(post)!=3:
        raise ValueError("missing three-account atomic post-state")
    final=[]
    for account,mint in zip(post,mints):
        if not isinstance(account,dict) or account.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("unexpected simulated token account owner")
        encoded=account.get("data")
        if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
            raise ValueError("missing simulated SPL token account data")
        state=decode_token_account(base64.b64decode(encoded[0],validate=True))
        if state["mint"]!=mint:
            raise ValueError("simulated token mint continuity mismatch")
        final.append(state["amount_base_units"])
    spent=initial_input-final[0]
    gained=final[2]-initial_output
    if not 0<spent<=max_input or gained<minimum_output:
        raise ValueError("atomic swap did not meet input/output balance constraints")
    if final[1]<initial_intermediate:
        raise ValueError("intermediate token account was depleted beyond initial balance")
    return {"signed_atomic_simulation_verified":True,
            "first_program":first_program,"second_program":second_program,
            "spent_input_base_units":spent,"received_output_base_units":gained,
            "intermediate_post_balance":final[1],
            "intermediate_intra_transaction_consumption_verified":False,
            "instruction_order_verified":False,
            "rollback_failure_case_verified":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False}
