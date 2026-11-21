"""Authenticate canonical PumpSwap FeeConfig PDA and its program owner.

FeeConfig PDA seeds ['fee_config', PumpSwap program id] belong to pump_fees.
Official docs: pump-public-docs/docs/instructions/MULTI_HOP_SWAP.md.
Account authentication does not establish which fee schedule applies.
"""
import base64
from arb.rpc import call
from arb.pumpswap_fee_config import decode

PROGRAM="pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"
ADDRESS="5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx"


def authenticated_address():
    from solders.pubkey import Pubkey
    from arb.pumpswap_pool import PROGRAM as PUMP
    derived,bump=Pubkey.find_program_address(
        [b"fee_config",bytes(Pubkey.from_string(PUMP))],Pubkey.from_string(PROGRAM))
    if str(derived)!=ADDRESS:
        raise ValueError("Pump FeeConfig PDA mismatch")
    return ADDRESS,bump


def decode_authenticated(account, *, address):
    expected,bump=authenticated_address()
    if address!=expected or not isinstance(account,dict) or (
            account.get("owner")!=PROGRAM or account.get("executable") is not False):
        raise ValueError("unauthenticated Pump FeeConfig account")
    encoded=account.get("data")
    if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
        raise ValueError("invalid Pump FeeConfig RPC encoding")
    config=decode(base64.b64decode(encoded[0],validate=True))
    if config["bump"]!=bump:
        raise ValueError("Pump FeeConfig bump mismatch")
    return {**config,"account_authenticated":True,"address":expected,
            "effective_fee_verified":False}


def fetch(rpc):
    address,_=authenticated_address()
    response=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}])
    slot=response.get("context",{}).get("slot")
    if type(slot) is not int or slot<0:
        raise ValueError("missing Pump FeeConfig RPC slot")
    return {**decode_authenticated(response.get("value"),address=address),"slot":slot}
