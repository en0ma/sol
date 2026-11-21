"""Strict Serum/OpenBook v3 OpenOrders balances for Raydium AMM v4.

Account size and padding, flags, market identity and account owner must match
the manifest-captured pool-linked market. Effective AMM reserves equal vault
balances + OpenOrders totals - pool pending PnL. No orderbook fills modeled.
"""
import base64
from arb.orca_whirlpool import b58
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
SIZE=3228
def decode_open_orders(raw,*,market,owner):
    if type(raw)is not bytes or len(raw)!=SIZE or raw[:5]!=b"serum" or raw[-7:]!=b"padding":
        raise ValueError("unsupported Serum v3 OpenOrders account layout")
    u64=lambda off:int.from_bytes(raw[off:off+8],"little")
    flags=u64(5)
    if flags&0x5!=0x5 or flags&0x2 or flags&~0x5:
        raise ValueError("OpenOrders not initialized or wrong account kind")
    if b58(raw[13:45])!=market or b58(raw[45:77])!=owner:
        raise ValueError("OpenOrders market or authority mismatch")
    base_free,base_total,quote_free,quote_total=(u64(77),u64(85),u64(93),u64(101))
    if base_free>base_total or quote_free>quote_total:
        raise ValueError("OpenOrders free balance exceeds total")
    return {"base_token_total":base_total,"quote_token_total":quote_total,
            "base_token_free":base_free,"quote_token_free":quote_free}
def adjusted_reserves(fixture,pool):
    from arb.source_snapshot_manifest import verify
    verify(fixture)
    if pool.get("venue")!="raydium_amm_v4":
        raise ValueError("requires Raydium AMM v4 fundamental")
    state=pool["decoded_pool_state"]
    if pool.get("address") not in fixture["state_account_addresses"]:
        raise ValueError("pool missing from contextual source inventory")
    # Derive the AMM authority from pool nonce and fixed program ID, not
    # from an untrusted caller argument. The OpenOrders authority must match.
    from solders.pubkey import Pubkey
    from arb.raydium_amm_v4_preflight import PROGRAM
    nonce=state.get("nonce")
    if type(nonce)is not int or not 0<=nonce<=255:
        raise ValueError("AMM v4 authority nonce invalid")
    open_orders_owner=str(Pubkey.create_program_address(
        [b"amm authority",bytes([nonce])],Pubkey.from_string(PROGRAM)))
    address=state["open_orders"]
    if address not in fixture["state_account_addresses"]:
        raise ValueError("OpenOrders missing from same-slot inventory")
    acct=fixture["accounts"][address]
    if acct.get("owner")!=state["market_program"] or acct.get("executable") is not False:
        raise ValueError("OpenOrders market program owner missing")
    encoded=acct.get("data")
    if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
        raise ValueError("OpenOrders data invalid")
    oo=decode_open_orders(base64.b64decode(encoded[0],validate=True),
                          market=state["market_id"],owner=open_orders_owner)
    balances=pool["vault_base_units"]
    if not isinstance(balances,list) or len(balances)!=2 or any(type(x)is not int or x<=0 for x in balances):
        raise ValueError("unverified vault reserves")
    net=[balances[0]+oo["base_token_total"]-state["base_need_take_pnl"],
         balances[1]+oo["quote_token_total"]-state["quote_need_take_pnl"]]
    if any(type(v)is not int or not 0<v<2**64 for v in net):
        raise ValueError("invalid net AMM v4 reserves")
    return {"effective_reserves_base_units":net,
            "open_orders_authority":open_orders_owner,
            "market_accounts_authenticated":True,
            "effective_reserves_authenticated":True,
            "source":"MANIFEST_CAPTURED_SERUM_V3_OPENORDERS_AND_POOL_PNL",
            "actual_signed_quote_parity_verified":False,**SAFE}
