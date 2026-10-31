"""Attempt actual source-native multihop quotes; never promote unavailable pricing.

The source discovery report authenticates *topology*, not all fee/tick/bin
accounts. Quote execution is independently gated per leg; blocked inputs
remain visible and are not replaced with fabricated prices.
"""
from arb.m5_authenticated_native_route_chain import chain
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def attempt(report, *, amounts=(10000,100000,1000000), quote_leg):
    if (not isinstance(report,dict) or
            report.get("status")!="SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY"
            or any(report.get(k)is not False for k in SAFE)
            or not isinstance(report.get("routes"),list)
            or not callable(quote_leg) or not isinstance(amounts,(list,tuple))
            or not 1<=len(amounts)<=8 or any(type(a)is not int or not 0<a<2**64 for a in amounts)):
        raise ValueError("authenticated source graph and exact-input quote provider required")
    rows=[]
    for route_index,route in enumerate(report["routes"]):
        for amount in amounts:
            try:
                quoted=chain(route,initial_input=amount,quote_leg=quote_leg)
                rows.append({"route_index":route_index,"hops":route["hops"],
                    "initial_input":amount,"status":"FULL_NATIVE_QUOTE_UNSIMULATED",
                    "final_output":quoted["final_output"],
                    "snapshot_slot":quoted["snapshot_slot"],
                    "source_quote_verified":True,"signed_simulation_verified":False,
                    "net_profitable_verified":False,**SAFE})
            except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
                rows.append({"route_index":route_index,"hops":route.get("hops"),
                    "initial_input":amount,"status":"NATIVE_QUOTE_BLOCKED",
                    "reason":str(exc)[:240],"source_quote_verified":False,
                    "signed_simulation_verified":False,
                    "net_profitable_verified":False,**SAFE})
    return {"status":"SOURCE_NATIVE_ROUTE_QUOTE_ATTEMPTS",
            "source_route_count":len(report["routes"]),
            "attempt_count":len(rows),
            "full_native_quote_count":sum(r["source_quote_verified"] for r in rows),
            "net_profitable_verified_count":0,
            "attempts":rows,**SAFE}
