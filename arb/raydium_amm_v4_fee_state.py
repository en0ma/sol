"""Captured Raydium AMM v4 AMM state fee decoding, fail closed.

LiquidityStateV4 contains swap_fee_numerator/denominator u64 at byte
offsets 176/184. Convert exactly to fee ppm only when no precision is lost.
This is indicative pool-state fee, not validated signed swap parity.
"""
from fractions import Fraction
from arb.raydium_amm_v4 import decode as decode_pool
from arb.raydium_amm_v4_open_orders_reserves import adjusted_reserves
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_pool_fundamentals import extract
from arb.source_snapshot_manifest import verify
import base64
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def fee_fraction_from_raw_pool(raw):
    """Lossless native u64 fee numerator/denominator; no ppm quantization."""
    if not isinstance(raw,(bytes,bytearray)) or len(raw)<192:
        raise ValueError("AMM v4 pool native fee bytes absent")
    decode_pool(raw)
    numerator=int.from_bytes(raw[176:184],"little")
    denominator=int.from_bytes(raw[184:192],"little")
    if denominator<=0 or not 0<numerator<denominator:
        raise ValueError("invalid AMM v4 native swap fee")
    return numerator,denominator

def quote_native_fraction(reserves,mints,input_mint,amount_in,numerator,denominator):
    """Exact integer rational-fee CPMM reference (still indicative)."""
    if (not isinstance(reserves,list) or len(reserves)!=2
            or any(type(r)is not int or r<=0 for r in reserves)
            or not isinstance(mints,list) or len(mints)!=2
            or len(set(mints))!=2 or input_mint not in mints
            or type(amount_in)is not int or not 0<amount_in<2**64
            or type(numerator)is not int or type(denominator)is not int
            or not 0<numerator<denominator):
        raise ValueError("invalid native AMM v4 quote state")
    i=mints.index(input_mint)
    effective=amount_in*(denominator-numerator)
    output=reserves[1-i]*effective//(reserves[i]*denominator+effective)
    if not 0<output<reserves[1-i]:
        raise ValueError("AMM v4 native quote dust/empty pool")
    return {"amount_out":output,
            "fee_numerator":numerator,"fee_denominator":denominator,
            "fee_floor_input_units":amount_in*numerator//denominator,
            "fee_ceiling_input_units":(amount_in*numerator+denominator-1)//denominator}

def fee_from_raw_pool(raw):
    numerator,denominator=fee_fraction_from_raw_pool(raw)
    value=Fraction(numerator*1000000,denominator)
    if value.denominator!=1 or not 0<value.numerator<1000000:
        raise ValueError("AMM v4 fee cannot be represented exactly in ppm")
    return value.numerator
def derive_v4(fixture):
    verify(fixture)
    rows=extract_pool_states(fixture)
    funds=extract(fixture)["fundamentals"]
    results=[]
    lookup={(fund["venue"],fund["address"]):fund for fund in funds}
    if len(lookup)!=len(funds):
        raise ValueError("duplicate native liquidity source")
    for row in rows:
        if row["venue"]!="raydium_amm_v4":continue
        f=lookup.get((row["venue"],row["address"]))
        if (not f or f["mints"]!=row["mints"] or
                f["snapshot_slot"]!=row["snapshot_slot"]):
            raise ValueError("AMM v4 quote native source binding mismatch")
        addr=row["address"]
        raw=base64.b64decode(fixture["accounts"][addr]["data"][0],validate=True)
        numerator,denominator=fee_fraction_from_raw_pool(raw)
        fee=fee_from_raw_pool(raw)
        reserve=adjusted_reserves(fixture,{**row,"vault_base_units":f["vault_base_units"]})
        results.append({"venue":"raydium_amm_v4","address":addr,"mints":row["mints"],
          "slot":row["snapshot_slot"],"trade_fee_ppm":fee,
          "native_fee_numerator":numerator,"native_fee_denominator":denominator,
          "trade_fee_authenticated":True,**reserve})
    return {"status":"AMM_V4_ACCOUNT_DERIVED_INDICATIVE_PRICING",
        "pricing":results,"signed_quote_parity_verified":False,**SAFE}
