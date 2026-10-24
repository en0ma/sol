"""Fail-closed Raydium AMM v4 source-fork vault and OpenBook market preflight.

Authenticates the AMM pool, classic SPL vaults, market ownership, and market
book account ownership in one getMultipleAccounts snapshot. The vault signer
and authority are supplied by independently validated PDAs; until verified,
execution evidence must stay blocked.
"""
import base64
from arb.rpc import call
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
from arb.raydium_amm_v4 import decode
from arb.venue_watchlist import RECOGNIZED_UNSUPPORTED

PROGRAM=next(k for k,v in RECOGNIZED_UNSUPPORTED.items() if v=="raydium_amm_v4")

def verify_pool_market(rpc,pool,state):
    required=("base_vault","quote_vault","open_orders","market_id",
              "base_mint","quote_mint","market_program")
    if not isinstance(state,dict) or any(not isinstance(state.get(k),str) or not state[k] for k in required):
        raise ValueError("AMM v4 required authenticated pool fields missing")
    addresses=[pool,state["base_vault"],state["quote_vault"],
               state["open_orders"],state["market_id"]]
    response=call(rpc,"getMultipleAccounts",[addresses,{"encoding":"base64","commitment":"confirmed"}])
    values=response.get("value") if isinstance(response,dict) else None
    slot=response.get("context",{}).get("slot") if isinstance(response,dict) else None
    if type(slot) is not int or not isinstance(values,list) or len(values)!=len(addresses):
        raise ValueError("AMM v4 synchronized source snapshot unavailable")
    if any(not isinstance(v,dict) or v.get("executable") is not False or
           not isinstance(v.get("data"),list) or v["data"][1]!="base64"
           for v in values):
        raise ValueError("AMM v4 required market accounts missing")
    if values[0].get("owner")!=PROGRAM or decode(base64.b64decode(values[0]["data"][0],validate=True))!=state:
        raise ValueError("AMM v4 pool owner or state changed")
    for idx,mint in ((1,state["base_mint"]),(2,state["quote_mint"])):
        if values[idx].get("owner")!=TOKEN_PROGRAM:
            raise ValueError("AMM v4 vault owner is not classic SPL")
        token=decode_token_account(base64.b64decode(values[idx]["data"][0],validate=True))
        if token["mint"]!=mint or token["amount_base_units"]<=0:
            raise ValueError("AMM v4 vault mint or balance mismatch")
    if values[3].get("owner")!=state["market_program"] or values[4].get("owner")!=state["market_program"]:
        raise ValueError("AMM v4 OpenOrders or market must both be owned by the authenticated market program")
    return {"slot":slot,"pool_and_market_authenticated":True,
            "market_accounts_authenticated":False,
            "signed_atomic_simulation_verified":False,"broadcast":False}
