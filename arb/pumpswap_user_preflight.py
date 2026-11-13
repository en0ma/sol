"""Validate existing user token accounts before signing a local PumpSwap swap.

Balances and mints are fetched in one slot-consistent RPC response. Any
nonexistent, wrong-owner or mismatched input/output account fails closed.
"""
import base64
from arb.rpc import call
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
from arb.pumpswap_local_simulation import local_rpc_only


def verify_user_accounts(rpc, user, input_address, output_address,
                         input_mint, output_mint, expected_input, expected_output):
    local_rpc_only(rpc)
    if (not isinstance(user,str) or not user or input_address==output_address
            or input_mint==output_mint
            or any(type(n) is not int or n<0 or n>=1<<64
                   for n in (expected_input,expected_output))):
        raise ValueError("invalid pre-simulation user account specification")
    response=call(rpc,"getMultipleAccounts",[
        [input_address,output_address],{"encoding":"base64","commitment":"confirmed"}])
    items=response.get("value")
    slot=response.get("context",{}).get("slot")
    if type(slot) is not int or not isinstance(items,list) or len(items)!=2:
        raise ValueError("incomplete local user token snapshot")
    for i,(item,mint,amount) in enumerate(zip(
            items,(input_mint,output_mint),(expected_input,expected_output))):
        if (not isinstance(item,dict) or item.get("owner")!=TOKEN_PROGRAM
                or item.get("executable") is not False):
            raise ValueError("user token account missing or wrong program")
        encoded=item.get("data")
        if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
            raise ValueError("user token account encoding mismatch")
        decoded=decode_token_account(base64.b64decode(encoded[0],validate=True))
        if (decoded["mint"]!=mint or decoded["authority"]!=user
                or decoded["amount_base_units"]!=amount):
            raise ValueError("user token mint, authority or balance changed")
    return {"slot":slot,"user_accounts_verified":True}
