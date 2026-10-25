"""M5 independent indicative quote vs signed offline atomic swap reconciliation.

An independently accepted signed receipt does not prove that it executed the
same pools, mints, size or fork snapshot as a new opportunity quote.
This checker requires *both* atomic proof and route/amount provenance.
No positive quote alone is promoted to profitability or live execution.
"""
from arb.next_ten_atomic_evidence import assess
SAFETY={"actionable":False,"live_execution_approved":False,"broadcast":False}

def reconcile(route,quotes,receipt,*,tolerance_bps=100):
    reasons=[]
    if not isinstance(route,dict) or not isinstance(quotes,list) or len(quotes)!=2 or not isinstance(receipt,dict):
        return {"status":"UNVERIFIED","reasons":["two-leg route, quotes and receipt required"],**SAFETY}
    legs=route.get("legs")
    if not isinstance(legs,list) or len(legs)!=2 or any(not isinstance(e,dict) for e in legs):
        return {"status":"UNVERIFIED","reasons":["valid two-leg route required"],**SAFETY}
    if type(tolerance_bps)is not int or not 0<=tolerance_bps<=10000:
        raise ValueError("invalid quote-error tolerance")
    venues=tuple(e.get("venue") for e in legs)
    proof=assess(venues,receipt)
    if proof["status"]!="VERIFIED":
        reasons.append("independent signed atomic evidence invalid")
    pools=[e.get("pool") for e in legs]
    if receipt.get("route_pool_addresses")!=pools:
        reasons.append("signed receipt pool identities absent/mismatched")
    mints=[legs[0].get("input_mint"),legs[0].get("output_mint"),legs[1].get("output_mint")]
    if legs[1].get("input_mint")!=mints[1] or mints[0]!=mints[-1] or receipt.get("route_mints")!=mints:
        reasons.append("route and signed receipt mint identities mismatch")
    slots=[q.get("snapshot_slot") for q in quotes if isinstance(q,dict)]
    if len(slots)!=2 or any(type(s)is not int for s in slots) or len(set(slots))!=1 or receipt.get("source_snapshot_slot")!=slots[0]:
        reasons.append("same-slot source/receipt provenance absent")
    for i,(edge,q) in enumerate(zip(legs,quotes)):
        if not isinstance(q,dict) or any(q.get(k)!=edge.get(k) for k in ("venue","pool","input_mint","output_mint")):
            reasons.append(f"quote leg {i} identity mismatch")
    amounts=[q.get("amount_in") for q in quotes if isinstance(q,dict)]
    outputs=[q.get("amount_out") for q in quotes if isinstance(q,dict)]
    if (len(amounts)!=2 or len(outputs)!=2 or
            any(type(x)is not int or x<=0 for x in amounts+outputs) or amounts[1]!=outputs[0]):
        reasons.append("quote amount continuity absent")
    initial=receipt.get("initial_balances_base_units")
    final=receipt.get("positive_post_balances_base_units")
    observed_input=observed_output=None
    if (isinstance(initial,list) and len(initial)==3 and
        isinstance(final,list) and len(final)==3 and
        all(type(x)is int and x>=0 for x in initial+final)):
        observed_input=initial[0]-final[0]
        observed_output=final[2]-initial[2]
    if observed_input is None or observed_input<=0 or observed_output is None or observed_output<=0:
        reasons.append("actual SPL initial/final deltas absent")
    elif len(amounts)==2 and observed_input!=amounts[0]:
        reasons.append("executed input differs from quoted input")
    deviation=None
    if observed_output is not None and observed_output>0 and len(outputs)==2 and type(outputs[-1])is int and outputs[-1]>0:
        deviation=abs(outputs[-1]-observed_output)*10000//outputs[-1]
        if abs(outputs[-1]-observed_output)*10000>tolerance_bps*outputs[-1]:
            reasons.append("quote vs simulated final SPL output exceeds tolerance")
    else:
        reasons.append("positive quoted and observed output required")
    return {"status":"RECONCILED_SIGNED_SIMULATION" if not reasons else "UNVERIFIED",
            "reasons":reasons,"quoted_final_output_base_units":outputs[-1] if len(outputs)==2 else None,
            "simulated_final_output_base_units":observed_output,
            "quote_deviation_bps":deviation,"signed_atomic_evidence_status":proof["status"],
            "route_snapshot_consistent":not any("provenance" in r for r in reasons),
            "simulation_only":True,"profitability_confirmed":False,**SAFETY}
