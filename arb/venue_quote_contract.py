"""Shared exact-input quote evidence contract; not a quote oracle.

Providers for each of seven venues must fill this from authenticated snapshot
math. This validator refuses missing fees, direction, liquidity and stale slot
provenance; it never substitutes spot-price multiplication for swap math.
"""
from arb.execution_target_matrix import TARGET_VENUES
SAFETY={"actionable":False,"live_execution_approved":False,"broadcast":False}

def validate(quote,pool,*,requested_input,now,max_age=60):
    if not isinstance(quote,dict) or not isinstance(pool,dict):
        raise ValueError("quote and authenticated pool required")
    reasons=[]
    for k in ("venue","pool","input_mint","output_mint"):
        expected=pool.get("address") if k=="pool" else pool.get(k)
        if k in ("input_mint","output_mint"):
            continue
        if quote.get(k)!=expected:reasons.append(k+" identity mismatch")
    if quote.get("venue") not in TARGET_VENUES:reasons.append("unsupported quote venue")
    mints=pool.get("mints",[])
    if not isinstance(mints,(list,tuple)) or len(mints)!=2 or (
        quote.get("input_mint"),quote.get("output_mint")) not in ((mints[0],mints[1]),(mints[1],mints[0])):
        reasons.append("quote mint direction mismatch")
    if type(requested_input)is not int or requested_input<=0 or quote.get("amount_in")!=requested_input:
        reasons.append("quote exact input mismatch")
    for key in ("amount_out","fee_input_units","liquidity_input_units","price_impact_bps"):
        val=quote.get(key)
        if type(val)is not int or val<0 or (key in ("amount_out","liquidity_input_units") and val==0):
            reasons.append("invalid or unpriced "+key)
    if type(quote.get("price_impact_bps"))is int and quote["price_impact_bps"]>10000:
        reasons.append("price impact exceeds 10000bps")
    if type(quote.get("liquidity_input_units"))is int and type(requested_input)is int and requested_input>quote["liquidity_input_units"]:
        reasons.append("insufficient liquidity")
    if quote.get("source_authenticated") is not True or quote.get("snapshot_slot")!=pool.get("slot"):
        reasons.append("quote snapshot not authenticated or slot mismatch")
    t=quote.get("observed_unix")
    if type(t)is not int or type(now)is not int or type(max_age)is not int or max_age<1 or t>now or now-t>max_age:
        reasons.append("stale/future quote")
    if not isinstance(quote.get("quote_model"),str) or not quote["quote_model"]:
        reasons.append("missing venue-specific quote model")
    return {"status":"VALIDATED_INDICATIVE_QUOTE" if not reasons else "UNASSESSABLE",
            "reason_codes":reasons,"quote":quote if not reasons else None,
            "execution_verified":False,**SAFETY}
