"""Fail-closed signed standalone swap simulation for authenticated SPL venues.

Consumes an already-signed transaction, never broadcasts, and checks actual
simulated user token-account post-state. No quote, fee or profitability approval.
"""
import base64
from arb.pumpswap_local_simulation import local_rpc_only
from arb.rpc import call
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account

def verify_signed_swap(rpc,signed_bytes,*,program,input_account,output_account,
                       input_mint,output_mint,initial_input,initial_output,
                       max_input,min_output):
    local_rpc_only(rpc)
    if not isinstance(signed_bytes,bytes) or not signed_bytes or len(signed_bytes)>1232:
        raise ValueError("signed swap transaction missing or too large")
    if (any(not isinstance(x,str) or not x for x in
            (program,input_account,output_account,input_mint,output_mint))
            or input_account==output_account or input_mint==output_mint):
        raise ValueError("invalid signed swap account or mint identity")
    values=(initial_input,initial_output,max_input,min_output)
    if (any(type(v)is not int or v<0 or v>=1<<64 for v in values)
            or max_input<=0 or min_output<=0 or initial_input<max_input):
        raise ValueError("invalid signed swap amounts or thresholds")
    from solders.transaction import Transaction
    try:
        tx=Transaction.from_bytes(signed_bytes)
        tx.verify()
        keys=tx.message.account_keys
        invoked=[str(keys[ix.program_id_index]) for ix in tx.message.instructions]
        if invoked.count(program)!=1:
            raise ValueError("expected exactly one signed venue instruction")
        from solders.pubkey import Pubkey
        key_in=Pubkey.from_string(input_account)
        key_out=Pubkey.from_string(output_account)
        if key_in not in keys or key_out not in keys:
            raise ValueError("signed swap user token account absent from transaction")
        venue_ix=tx.message.instructions[invoked.index(program)]
        if (keys.index(key_in) not in venue_ix.accounts
                or keys.index(key_out) not in venue_ix.accounts):
            raise ValueError("signed venue instruction must reference both user token accounts")
    except Exception as exc:
        raise ValueError("invalid signed standalone swap instruction or signature") from exc
    response=call(rpc,"simulateTransaction",[
        base64.b64encode(signed_bytes).decode(),
        {"encoding":"base64","sigVerify":True,"replaceRecentBlockhash":False,
         "accounts":{"encoding":"base64","addresses":[input_account,output_account]}}])
    value=response.get("value") if isinstance(response,dict) else None
    if not isinstance(value,dict) or value.get("err") is not None:
        raise ValueError("signed standalone swap simulation failed")
    logs=value.get("logs")
    if not isinstance(logs,list) or not any(
            line.startswith("Program "+program+" invoke [") for line in logs):
        raise ValueError("signed venue invocation not observed")
    if not any(line=="Program "+program+" success" for line in logs):
        raise ValueError("signed venue success not observed")
    accounts=value.get("accounts")
    if not isinstance(accounts,list) or len(accounts)!=2:
        raise ValueError("signed swap post-state missing")
    amounts=[]
    for account,mint in zip(accounts,(input_mint,output_mint)):
        if not isinstance(account,dict) or account.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("post-state token account program mismatch")
        encoded=account.get("data")
        if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
            raise ValueError("post-state token account encoding mismatch")
        token=decode_token_account(base64.b64decode(encoded[0],validate=True))
        if token["mint"]!=mint:
            raise ValueError("post-state token mint mismatch")
        amount=token["amount_base_units"]
        if type(amount)is not int or not 0<=amount<1<<64:
            raise ValueError("post-state token balance invalid")
        amounts.append(amount)
    spent=initial_input-amounts[0]
    received=amounts[1]-initial_output
    if not 0<spent<=max_input or received<min_output:
        raise ValueError("signed swap post-state did not satisfy input/output constraints")
    return {"signed_standalone_simulation_verified":True,
            "spent_input_base_units":spent,"received_output_base_units":received,
            "min_output_base_units":min_output,
            "executable_quote":False,"fee_mode_verified":False,
            "profitable_arbitrage_verified":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False}
