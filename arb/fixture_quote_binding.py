"""Bind indicative quotes to exact captured source-state fixture integrity.

Does not create quotes from raw account bytes, attest chain authenticity, or
claim that source-state snapshot is identical to Surfpool execution time.
"""
from arb.source_snapshot_manifest import verify
SAFETY={"actionable":False,"live_execution_approved":False,"broadcast":False}
def bind(fixture,route,quotes):
    if not isinstance(fixture,dict) or not isinstance(route,dict) or not isinstance(quotes,list) or len(quotes)!=2:
        raise ValueError("complete fixture route and two quotes required")
    verify(fixture)
    legs=route.get("legs")
    if not isinstance(legs,list) or len(legs)!=2:
        raise ValueError("exact two-leg route required")
    pools=[fixture.get("first_pool"),fixture.get("second_pool")]
    venues=[fixture.get("first_venue"),fixture.get("second_venue")]
    mints=fixture.get("route_mints")
    slot=fixture.get("state_accounts_observed_slot")
    if (any(type(x)is not str or not x for x in pools+venues) or
        not isinstance(mints,list) or len(mints)!=3 or
        mints[0]!=mints[2] or mints[0]==mints[1]):
        raise ValueError("invalid source route provenance")
    for i,(leg,q) in enumerate(zip(legs,quotes)):
        if not isinstance(leg,dict) or not isinstance(q,dict):
            raise ValueError("invalid leg quote")
        expected={"venue":venues[i],"pool":pools[i],"input_mint":mints[i],
                  "output_mint":mints[i+1]}
        if any(leg.get(k)!=v or q.get(k)!=v for k,v in expected.items()):
            raise ValueError("fixture route and quote identity mismatch")
        if q.get("snapshot_slot")!=slot or q.get("source_authenticated") is not True:
            raise ValueError("quote not sourced from the contextual state snapshot")
        if type(q.get("amount_in"))is not int or type(q.get("amount_out"))is not int or q["amount_in"]<=0 or q["amount_out"]<=0:
            raise ValueError("invalid quoted amounts")
    if quotes[0]["amount_out"]!=quotes[1]["amount_in"]:
        raise ValueError("quote route amount continuity mismatch")
    return {"status":"FIXTURE_QUOTE_IDENTITY_BOUND_ONLY",
            "source_manifest_sha256":fixture["state_account_manifest_sha256"],
            "state_accounts_observed_slot":slot,
            "source_account_count":fixture["state_account_count"] if type(fixture.get("state_account_count"))is int else None,
            "protocol_quote_from_raw_fixture_verified":False,
            "signed_execution_quote_accuracy_verified":False,**SAFETY}
