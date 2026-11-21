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

def authenticate_swap_market(rpc,pool,state):
    """Decode and verify legacy Serum/OpenBook market swap roles from source RPC."""
    from solders.pubkey import Pubkey
    from arb.orca_whirlpool import b58
    market=state["market_id"]
    program=state["market_program"]
    result=call(rpc,"getAccountInfo",[market,{"encoding":"base64","commitment":"confirmed"}])
    info=result.get("value") if isinstance(result,dict) else None
    if not isinstance(info,dict) or info.get("owner")!=program or info.get("executable") is not False:
        raise ValueError("AMM v4 source market missing or wrong owner")
    raw=base64.b64decode(info["data"][0],validate=True)
    # Serum v3 MarketState layout: 5-byte padding + 376-byte base state.
    if len(raw)<388 or raw[:5]!=b"serum" or raw[-7:]!=b"padding":
        raise ValueError("AMM v4 market does not have legacy Serum account padding")
    flags=int.from_bytes(raw[5:13],"little")
    if flags & 3 != 3:
        raise ValueError("AMM v4 source market flags do not identify initialized market")
    def key(start):return b58(raw[start:start+32])
    if key(13)!=market or {key(53),key(85)}!={state["base_mint"],state["quote_mint"]}:
        raise ValueError("AMM v4 market identity or mints mismatch")
    if key(53)!=state["base_mint"] or key(85)!=state["quote_mint"]:
        raise ValueError("AMM v4 market base/quote orientation mismatch")
    nonce=int.from_bytes(raw[45:53],"little")
    signer=str(Pubkey.create_program_address(
        [bytes(Pubkey.from_string(market)),nonce.to_bytes(8,"little")],
        Pubkey.from_string(program)))
    roles={"market_base_vault":key(117),"market_quote_vault":key(165),
           "market_event_queue":key(253),"market_bids":key(285),"market_asks":key(317),
           "market_vault_signer":signer}
    accounts=[roles[x] for x in ("market_bids","market_asks","market_event_queue",
                                  "market_base_vault","market_quote_vault")]
    if len(set(accounts))!=len(accounts):
        raise ValueError("AMM v4 market role accounts are duplicated")
    response=call(rpc,"getMultipleAccounts",[accounts,{"encoding":"base64","commitment":"confirmed"}])
    values=response.get("value") if isinstance(response,dict) else None
    slot=response.get("context",{}).get("slot") if isinstance(response,dict) else None
    if type(slot)is not int or not isinstance(values,list) or len(values)!=5:
        raise ValueError("AMM v4 market roles snapshot missing")
    for i in range(3):
        if not isinstance(values[i],dict) or values[i].get("owner")!=program or values[i].get("executable") is not False:
            raise ValueError("AMM v4 orderbook/event role owner mismatch")
    for i,mint in ((3,state["base_mint"]),(4,state["quote_mint"])):
        account=values[i]
        if not isinstance(account,dict) or account.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("AMM v4 market vault owner mismatch")
        token=decode_token_account(base64.b64decode(account["data"][0],validate=True))
        if token["mint"]!=mint or token["authority"]!=signer:
            raise ValueError("AMM v4 market vault mint or signer mismatch")
    amm_nonce=state["nonce"]
    amm_authority=str(Pubkey.create_program_address(
        [b"amm authority",bytes([amm_nonce])],Pubkey.from_string(PROGRAM)))
    roles["amm_authority"]=amm_authority
    return {"market_accounts_authenticated":True,"market_role_slot":slot,
            **roles,"market_role_addresses":accounts,
            "broadcast":False}
