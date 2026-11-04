"""Observed two-leg SPL output accuracy report for signed offline research.

Reports measured deviations even when source provenance is incomplete,
but does not promote unverified receipts into credible quote accuracy.
"""
from arb.quote_simulation_reconciliation import reconcile
from arb.signed_fixture_provenance_gate import audit
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def compare(fixture,route,quotes,receipt,*,tolerance_bps=100):
    if not isinstance(quotes,list) or len(quotes)!=2:
        raise ValueError("two exact-input quotes required")
    q0,q1=quotes
    amount=q0.get("amount_in") if isinstance(q0,dict) else None
    provenance=audit(fixture,receipt,quoted_first_input=amount)
    comparison=reconcile(route,quotes,receipt,tolerance_bps=tolerance_bps)
    first=receipt.get("first_leg_intermediate_received_base_units") if isinstance(receipt,dict) else None
    first_quote=q0.get("amount_out") if isinstance(q0,dict) else None
    last_quote=q1.get("amount_out") if isinstance(q1,dict) else None
    final=receipt.get("positive_post_balances_base_units") if isinstance(receipt,dict) else None
    initial=receipt.get("initial_balances_base_units") if isinstance(receipt,dict) else None
    last=(final[2]-initial[2] if isinstance(final,list) and isinstance(initial,list)
          and len(final)==len(initial)==3 and all(type(x)is int and x>=0 for x in final+initial) else None)
    def deviation(pred,actual):
        if type(pred)is not int or pred<=0 or type(actual)is not int or actual<0:
            return None
        return abs(actual-pred)*10000//pred
    return {"status":"DIAGNOSTIC_ONLY",
            "first_leg_quoted_output":first_quote,"first_leg_observed_output":first,
            "first_leg_deviation_bps":deviation(first_quote,first),
            "second_leg_quoted_output":last_quote,"second_leg_observed_output":last,
            "second_leg_deviation_bps":deviation(last_quote,last),
            "signed_atomic_evidence_status":comparison["signed_atomic_evidence_status"],
            "reconciliation_status":comparison["status"],
            "provenance_status":provenance["status"],
            "independent_source_to_execution_provenance_verified":False,
            "real_quote_accuracy_verified":False,**SAFE}
