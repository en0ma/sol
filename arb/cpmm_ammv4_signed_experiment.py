"""Exact-input, two-leg CPMM/AMM-v4 fixture quote experiment.

Both legs must obtain their own amounts from native account-derived
quote adapters; second quote consumes *first quoted output*. This produces
testable offline comparisons, never execution approvals or synthetic receipts.
"""
from arb.source_snapshot_manifest import verify
from arb.fixture_config_quote_projection import quote_cpmm_only
from arb.raydium_amm_v4_fixture_quote import quote_from_fixture
from arb.signed_quote_accuracy_report import compare
from arb.observed_signed_risk import screen
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
PAIR={"raydium_cpmm","raydium_amm_v4"}
def run(fixture,receipt,*,amount_in,observed_unix,costs_start_mint_units=None,tolerance_bps=100):
    verify(fixture)
    venues=(fixture.get("first_venue"),fixture.get("second_venue"))
    if set(venues)!=PAIR or venues[0]==venues[1]:
        raise ValueError("only CPMM / AMM v4 ordered pair supported")
    m=fixture.get("route_mints")
    if not isinstance(m,list) or len(m)!=3 or m[0]!=m[2] or m[0]==m[1]:
        raise ValueError("valid two-leg closed mint route required")
    if type(amount_in)is not int or not 0<amount_in<2**64 or type(observed_unix)is not int or observed_unix<0:
        raise ValueError("valid exact input and observation time required")
    legs=[{"venue":venues[i],"pool":fixture["first_pool" if i==0 else "second_pool"],
           "input_mint":m[i],"output_mint":m[i+1]} for i in (0,1)]
    quotes=[]
    for leg in legs:
        n=amount_in if not quotes else quotes[-1]["amount_out"]
        if type(n)is not int or n<=0:raise ValueError("zero first leg quote")
        if leg["venue"]=="raydium_cpmm":
            q=quote_cpmm_only(fixture,observed_unix=observed_unix,leg=leg,amount_in=n)["quote"]
        else:
            q=quote_from_fixture(fixture,pool=leg["pool"],input_mint=leg["input_mint"],
                amount_in=n,observed_unix=observed_unix)["quote"]
        if any(q.get(k)!=leg[k] for k in ("venue","input_mint","output_mint")) or q.get("pool")!=leg["pool"] or q.get("amount_in")!=n:
            raise ValueError("account quote and requested leg mismatch")
        if q.get("snapshot_slot")!=fixture["state_accounts_observed_slot"]:
            raise ValueError("cross-slot quote not permitted")
        quotes.append(q)
    route={"start_mint":m[0],"legs":legs}
    accuracy=compare(fixture,route,quotes,receipt,tolerance_bps=tolerance_bps)
    risk=None
    if accuracy["signed_atomic_evidence_status"]=="VERIFIED" and isinstance(costs_start_mint_units,dict):
        before=receipt.get("initial_balances_base_units")
        after=receipt.get("positive_post_balances_base_units")
        if (isinstance(before,list) and isinstance(after,list) and len(before)==len(after)==3 and
            all(type(x)is int and x>=0 for x in before+after) and before[0]>after[0] and after[2]>before[2]):
            risk=screen(input_units=before[0]-after[0],observed_output_units=after[2]-before[2],
                quoted_output_units=quotes[-1]["amount_out"],costs=costs_start_mint_units)
    return {"status":"ACCOUNT_DERIVED_SIGNED_PARITY_DIAGNOSTIC",
        "route":route,"quotes":quotes,"accuracy":accuracy,"observed_risk":risk,
        "account_snapshot_source_independently_attested":False,
        "protocol_exact_accuracy_verified":False,"profitability_confirmed":False,**SAFE}
