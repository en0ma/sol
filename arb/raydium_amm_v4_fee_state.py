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
def fee_from_raw_pool(raw):
    state=decode_pool(raw)
    numerator=int.from_bytes(raw[176:184],"little")
    denominator=int.from_bytes(raw[184:192],"little")
    if denominator<=0 or numerator>=denominator or numerator==0:
        raise ValueError("invalid onchain AMM v4 swap fee fraction")
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
        fee=fee_from_raw_pool(raw)
        reserve=adjusted_reserves(fixture,{**row,"vault_base_units":f["vault_base_units"]})
        results.append({"venue":"raydium_amm_v4","address":addr,"mints":row["mints"],
          "slot":row["snapshot_slot"],"trade_fee_ppm":fee,
          "trade_fee_authenticated":True,**reserve})
    return {"status":"AMM_V4_ACCOUNT_DERIVED_INDICATIVE_PRICING",
        "pricing":results,"signed_quote_parity_verified":False,**SAFE}
