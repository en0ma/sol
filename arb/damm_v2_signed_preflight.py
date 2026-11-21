"""Reauthenticate a DAMM v2 pool on Surfpool immediately before signing.

Caller-supplied decoder evidence is not a trusted execution authorization.
Refresh owner, decoder and vault checks on the local fork and enforce that
the state supplied to the builder matches the authenticated onchain snapshot.
No transaction is sent.
"""
import base64
from arb.pumpswap_local_simulation import local_rpc_only
from arb.rpc import call
from arb.meteora_damm_v2 import PROGRAM,decode,verify

def authenticate_pool(rpc,pool,state,evidence):
    local_rpc_only(rpc)
    if (not isinstance(pool,str) or not pool or not isinstance(state,dict)
            or not isinstance(evidence,dict)
            or evidence.get("venue")!="meteora_damm_v2"
            or evidence.get("address")!=pool
            or type(evidence.get("slot")) is not int or evidence["slot"]<0
            or type(evidence.get("vault_base_units")) is not list
            or len(evidence["vault_base_units"])!=2
            or evidence.get("mints")!=[state.get("token_a_mint"),state.get("token_b_mint")]):
        raise ValueError("missing authenticated DAMM v2 pool evidence")
    initial=call(rpc,"getAccountInfo",[
        pool,{"encoding":"base64","commitment":"confirmed",
              "minContextSlot":evidence["slot"]}])
    account=initial.get("value") if isinstance(initial,dict) else None
    slot=initial.get("context",{}).get("slot") if isinstance(initial,dict) else None
    if (type(slot)is not int or slot<evidence["slot"]
            or not isinstance(account,dict)
            or account.get("owner")!=PROGRAM
            or account.get("executable") is not False):
        raise ValueError("DAMM v2 pool owner or slot mismatch")
    encoded=account.get("data")
    if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
        raise ValueError("DAMM v2 pool encoding mismatch")
    current=decode(base64.b64decode(encoded[0],validate=True))
    if current!=state:
        raise ValueError("DAMM v2 builder state differs from onchain pool")
    fresh=verify(rpc,pool,current)
    if (fresh.get("venue")!="meteora_damm_v2"
            or fresh.get("address")!=pool
            or fresh.get("mints")!=evidence["mints"]
            or type(fresh.get("slot")) is not int or fresh["slot"]<slot
            or type(fresh.get("vault_base_units")) is not list
            or len(fresh["vault_base_units"])!=2
            or any(type(v)is not int or v<=0 for v in fresh["vault_base_units"])):
        raise ValueError("DAMM v2 refreshed vault evidence incomplete or stale")
    return {"pool_reauthenticated":True,"authenticated_slot":fresh["slot"],
            "fresh_vault_base_units":fresh["vault_base_units"],
            "actionable":False,"live_execution_approved":False,"broadcast":False}
