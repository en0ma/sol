"""Fail-closed local Surfpool simulation of a pre-signed PumpSwap transaction.

Never sends transactions; simulator must return explicit success and post-state.
Signing, swap account authentication and economic quote matching are separate.
"""
import base64
from urllib.parse import urlparse
from arb.rpc import call
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
from arb.pumpswap_pool import PROGRAM


def local_rpc_only(rpc):
    parsed=urlparse(rpc)
    if (parsed.scheme!="http" or parsed.hostname not in ("127.0.0.1","localhost")
            or parsed.port is None or parsed.username or parsed.password
            or parsed.path not in ("","/") or parsed.query or parsed.fragment):
        raise ValueError("PumpSwap simulation requires explicit localhost HTTP RPC")


def simulate_signed(rpc, signed_bytes, input_address, output_address,
                    input_mint, output_mint, initial_input, initial_output,
                    amount_in, *, min_amount_out=1):
    local_rpc_only(rpc)
    if (not isinstance(signed_bytes,bytes) or not signed_bytes
            or any(not isinstance(x,str) or not x for x in
                   (input_address,output_address,input_mint,output_mint))
            or input_address==output_address or input_mint==output_mint
            or any(type(x) is not int for x in (initial_input,initial_output,amount_in,min_amount_out))
            or min(initial_input,initial_output)>=1<<64
            or initial_input<amount_in or amount_in<=0 or initial_output<0
            or not 0<min_amount_out<1<<64):
        raise ValueError("invalid signed swap simulation inputs")
    value=call(rpc,"simulateTransaction",[
        base64.b64encode(signed_bytes).decode(),{"encoding":"base64",
        "sigVerify":True,"replaceRecentBlockhash":False,
        "accounts":{"encoding":"base64","addresses":[input_address,output_address]}}])["value"]
    if value.get("err") is not None:
        raise ValueError("PumpSwap simulation failed: "+str(value["err"]))
    logs=value.get("logs")
    if not isinstance(logs,list) or not any(
            "Program "+PROGRAM+" invoke" in line for line in logs):
        raise ValueError("PumpSwap program invocation not confirmed")
    accounts=value.get("accounts")
    if not isinstance(accounts,list) or len(accounts)!=2:
        raise ValueError("missing simulation post-state")
    amounts=[]
    for account,mint in zip(accounts,(input_mint,output_mint)):
        if not isinstance(account,dict) or account.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("simulated token account owner mismatch")
        encoded=account.get("data")
        if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
            raise ValueError("missing base64 simulation token data")
        state=decode_token_account(base64.b64decode(encoded[0],validate=True))
        if state["mint"]!=mint:
            raise ValueError("simulated token mint mismatch")
        amounts.append(state["amount_base_units"])
    spent=initial_input-amounts[0]
    gained=amounts[1]-initial_output
    if not 0<spent<=amount_in or gained<min_amount_out:
        raise ValueError("PumpSwap simulation did not satisfy swap deltas and output threshold")
    return {"simulation_verified":True,"spent_base_units":spent,
            "received_base_units":gained,"min_output_base_units":min_amount_out,"executable_quote":False,
            "profitable_arbitrage_verified":False}
