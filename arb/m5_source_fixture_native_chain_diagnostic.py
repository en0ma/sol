"""Drive multihop quote attempt accounting from real manifest-backed triangle legs.

This adapter deliberately refuses to upgrade indicative native quote output
into protocol-exact quote evidence. It exposes actual venue blockers per leg.
"""
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_all_venue_signed_quotes import quote_leg as fixture_quote_leg
from arb.m5_native_route_quote_attempts import attempt
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def inspect_fixture(fixture, *, observed_unix, amounts=(10000,100000,1000000)):
    rows=extract_pool_states(fixture)
    if len(rows)!=3 or type(observed_unix)is not int or observed_unix<0:
        raise ValueError("source-bound three-leg quote inventory required")
    mints=fixture.get("route_mints")
    if not isinstance(mints,list) or len(mints)!=4 or mints[0]!=mints[-1]:
        raise ValueError("closed source triangle required")
    legs=[{"venue":r["venue"],"pool":r["address"],
           "input":mints[i],"output":mints[i+1]} for i,r in enumerate(rows)]
    graph={"status":"SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY",
           "routes":[{"start_mint":mints[0],"hops":3,"legs":legs}],**SAFE}
    def native(leg,amount):
        index=next(i for i,row in enumerate(legs) if row is leg)
        q=fixture_quote_leg(fixture,leg_index=index,amount_in=amount,
                           observed_unix=observed_unix)
        if q.get("quote_status")!="SOURCE_BOUND_INDICATIVE":
            raise ValueError("leg %d %s: %s"%(index,leg["venue"],
                q.get("reason","native amount-aware source quote unavailable")))
        # Existing fixture adapter returns indicative, *not* protocol-exact
        # receipts. Never turn its predicted output into a passing quote.
        raise ValueError("leg %d %s: native source-bound quote indicative only"%(index,leg["venue"]))
    # Probe every captured leg independently at each initial amount. Chain
    # evaluation cannot reach leg 2 if leg 1 is unavailable, so independent
    # probes are essential to reveal the actual venue-specific blockers.
    leg_probes=[]
    for input_amount in amounts:
        for index,leg in enumerate(legs):
            observed=fixture_quote_leg(fixture,leg_index=index,
                amount_in=input_amount,observed_unix=observed_unix)
            status=observed.get("quote_status")
            leg_probes.append({"leg_index":index,"venue":leg["venue"],
                "pool":leg["pool"],"input_amount_base_units":input_amount,
                "status":status if status in ("SOURCE_BOUND_INDICATIVE","NATIVE_QUOTE_BLOCKED")
                         else "NATIVE_QUOTE_BLOCKED",
                "reason":observed.get("reason") if status=="NATIVE_QUOTE_BLOCKED"
                         else "indicative quote; protocol exactness unverified",
                "protocol_exact_verified":False,**SAFE})
    from collections import Counter
    counts=Counter((r["venue"],r["status"]) for r in leg_probes)
    per_venue={venue:{"indicative":counts[(venue,"SOURCE_BOUND_INDICATIVE")],
                       "blocked":counts[(venue,"NATIVE_QUOTE_BLOCKED")]}
               for venue in sorted({r["venue"] for r in leg_probes})}
    out=attempt(graph,amounts=amounts,quote_leg=native)
    return {**out,"fixture_source_slot":fixture["state_accounts_observed_slot"],
            "venue_sequence":[r["venue"] for r in rows],
            "independent_leg_probe_count":len(leg_probes),
            "independent_leg_probes":leg_probes,
            "venue_native_quote_probe_counts":per_venue,
            "fixture_native_protocol_exact_verified":False,**SAFE}
