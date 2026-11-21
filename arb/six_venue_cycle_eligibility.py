"""Read-only six-venue 2–6-hop graph eligibility preflight.

This boundary never declares a route executable: fresh venue-native fee/tick
quotes and independent signed offline simulation are separate required gates.
It bridges the existing provenance and fresh-source screening to the existing
atomic graph coordinator without building a second coordinator.
"""
from arb.six_venue_registry_eligibility import SIX_VENUES

SAFE = {"actionable":False,"live_execution_approved":False,"broadcast":False}


def screen_cycle_source_eligibility(legs, tokens, fresh_report):
    """Fail closed on stale/unsigned pool identities and disconnected graphs.

    Do not treat this result as a quote, trading approval or a full 2–6 leg
    acceptance. Repeated use of the SAME pool is blocked because later leg
    state would otherwise need to incorporate earlier simulated price impact.
    """
    if (not isinstance(legs,list) or not 2<=len(legs)<=6 or
        not isinstance(tokens,list) or len(tokens)!=len(legs)+1 or
        tokens[0]!=tokens[-1] or
        any(not isinstance(m,str) or not m for m in tokens) or
        any(tokens[i]==tokens[i+1] for i in range(len(legs)))):
        raise ValueError("closed 2-6 leg token cycle required")
    if (not isinstance(fresh_report,dict) or
        fresh_report.get("status")!="FRESH_IDENTITY_ONLY_NOT_USABLE_REGISTRY_ADMISSION" or
        fresh_report.get("coordinator_eligible_count")!=0 or
        any(fresh_report.get(k) is not False for k in SAFE) or
        not isinstance(fresh_report.get("source_authenticated"),list)):
        raise ValueError("fresh fail-closed identity report required")
    authenticated={}
    for pool in fresh_report["source_authenticated"]:
        if not isinstance(pool,dict):
            raise ValueError("malformed source-authenticated entry")
        key=(pool.get("venue"),pool.get("address"))
        if key in authenticated:
            raise ValueError("duplicate source pool identity")
        if (key[0] not in SIX_VENUES or not isinstance(key[1],str) or not key[1] or
            pool.get("source_identity_refreshed") is not True or
            pool.get("current_complete_fee_and_tick_state_verified") is not False or
            pool.get("current_native_sdk_signed_quote_verified") is not False or
            pool.get("coordinator_eligible") is not False or
            type(pool.get("current_source_slot")) is not int or
            pool["current_source_slot"]<0 or
            not isinstance(pool.get("mints"),list) or len(pool["mints"])!=2 or
            len(set(pool["mints"]))!=2):
            raise ValueError("untrusted incomplete source identity")
        authenticated[key]=pool
    used=set()
    for i,leg in enumerate(legs):
        if not isinstance(leg,dict):
            raise ValueError("malformed cycle leg")
        key=(leg.get("venue"),leg.get("pool"))
        if key in used:
            raise ValueError("repeated mutable pool requires sequential-state quote proof")
        used.add(key)
        if key not in authenticated:
            raise ValueError("unsigned or non-reauthenticated pool in cycle")
        if leg.get("input_mint")!=tokens[i] or leg.get("output_mint")!=tokens[i+1]:
            raise ValueError("disconnected cycle leg")
        if set(authenticated[key]["mints"])!={tokens[i],tokens[i+1]}:
            raise ValueError("fresh pool token-mint mismatch")
    return {"status":"SOURCE_IDENTITY_CYCLE_ONLY_PRICING_NOT_VERIFIED",
            "legs":len(legs),"pool_keys":[[r["venue"],r["pool"]] for r in legs],
            "fresh_source_identity_checked":True,
            "current_fee_liquidity_pricing_verified":False,
            "signed_full_route_verified":False,
            "coordinator_eligible":False,**SAFE}
