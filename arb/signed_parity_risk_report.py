"""Correlate signed quote parity and observed net-risk diagnostics in one report.

Both metrics are observations from offline tests; no real-market proof is implied.
"""
from arb.signed_quote_parity_portfolio import evaluate_cases
from arb.observed_signed_risk import screen
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def report(cases,*,as_of_unix,tolerance_bps=100):
    portfolio=evaluate_cases(cases,as_of_unix=as_of_unix,tolerance_bps=tolerance_bps)
    rows=[]
    for case,metric in zip(cases,portfolio["rows"]):
        receipt=case["receipt"]
        initial=receipt.get("initial_balances_base_units")
        final=receipt.get("positive_post_balances_base_units")
        costs=case.get("costs_start_mint_units")
        r=None
        # A failed/missing signed atomic proof cannot support observed PnL.
        signed_ok=metric.get("signed_atomic_evidence_status")=="VERIFIED"
        if (signed_ok and isinstance(initial,list) and isinstance(final,list) and
           len(initial)==len(final)==3 and
           all(type(x)is int and x>=0 for x in initial+final) and
           type(initial[0]-final[0])is int and initial[0]>final[0] and
           final[2]>initial[2] and isinstance(case.get("quotes"),list) and len(case["quotes"])==2):
            try:
                r=screen(input_units=initial[0]-final[0],
                         observed_output_units=final[2]-initial[2],
                         quoted_output_units=case["quotes"][1]["amount_out"],costs=costs)
            except (ValueError,KeyError,TypeError):
                pass
        rows.append({**metric,"observed_risk":r,
             "signed_observation_supported":signed_ok,
             "real_profitability_verified":False,**SAFE})
    return {"status":"SIGNED_OFFLINE_RESEARCH_DIAGNOSTIC",
            "rows":rows,"sample_count":len(rows),
            "protocol_accuracy_validated_count":0,
            "risk_validated_count":0,**SAFE}
