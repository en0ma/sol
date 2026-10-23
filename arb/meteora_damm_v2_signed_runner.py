"""Signed standalone Meteora DAMM v2 simulation against the local fork only.

Requires authenticated pool evidence and fresh user-account snapshot. Builder
availability is not proof of execution; the simulator must return real deltas.
"""
from arb.pumpswap_local_simulation import local_rpc_only
from arb.pumpswap_user_preflight import verify_user_accounts
from arb.meteora_damm_v2_swap import build_swap2
from arb.damm_v2_signed_preflight import authenticate_pool
from arb.signed_standalone_swap_verifier import verify_signed_swap

def sign_and_simulate(rpc,*,pool,state,evidence,payer,user_input,user_output,
                      initial_input,initial_output,amount_in,min_amount_out,
                      input_is_a):
    local_rpc_only(rpc)
    authentication=authenticate_pool(rpc,pool,state,evidence)
    if type(input_is_a)is not bool:
        raise ValueError("DAMM v2 swap direction required")
    mint_in=state["token_a_mint"] if input_is_a else state["token_b_mint"]
    mint_out=state["token_b_mint"] if input_is_a else state["token_a_mint"]
    verify_user_accounts(rpc,str(payer.pubkey()),user_input,user_output,
                         mint_in,mint_out,initial_input,initial_output)
    ix=build_swap2(pool,state,str(payer.pubkey()),user_input,user_output,
                   amount_in,min_amount_out,input_is_a=input_is_a)
    from solders.transaction import Transaction
    from solders.hash import Hash
    from arb.rpc import call
    latest=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    signed=Transaction.new_signed_with_payer(
        [ix],payer.pubkey(),[payer],Hash.from_string(latest))
    from arb.meteora_damm_v2 import PROGRAM
    result=verify_signed_swap(
        rpc,bytes(signed),program=PROGRAM,
        input_account=user_input,output_account=user_output,
        input_mint=mint_in,output_mint=mint_out,
        initial_input=initial_input,initial_output=initial_output,
        max_input=amount_in,min_output=min_amount_out)
    return {**result,**authentication,"venue":"meteora_damm_v2","local_only":True,
            "transaction_bytes":len(bytes(signed)),
            "actionable":False,"live_execution_approved":False,"broadcast":False}
