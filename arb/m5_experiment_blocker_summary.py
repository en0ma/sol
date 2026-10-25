"""Fail-closed prioritization of actual signed amount and quote blockers."""
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def summarize(rows):
    if not isinstance(rows,list):
        raise ValueError("diagnostic rows required")
    issues={}
    known={"SOURCE_FIXTURE_MISSING":"SOURCE_FIXTURE_MISSING",
           "SIGNED_RECEIPT_MISSING":"SIGNED_RECEIPT_MISSING",
           "SIGNED_SPL_BALANCES_UNAVAILABLE":"SIGNED_SPL_EVIDENCE_MISSING",
           "SOURCE_TO_EXECUTION_PROVENANCE_UNVERIFIED":"SOURCE_PROVENANCE_UNVERIFIED",
           "QUOTE_AND_SIGNED_OUTPUT_NOT_RECONCILED":"QUOTE_TO_SIGNED_UNRECONCILED",
           "SIGNED_SECOND_LEG_INPUT_DIFFERS_FROM_QUOTE":"QUOTE_AMOUNT_CONTINUITY_MISMATCH",
           "OBSERVED_INTERMEDIATE_UNCONSUMED":"SIGNED_INTERMEDIATE_REMAINDER"}
    def add(key,route):
        issues.setdefault(key,[]).append(route)
    for row in rows:
        route=row.get("route")
        if not isinstance(route,str):
            raise ValueError("route identity missing")
        if row.get("full_intermediate_consumption_observed") is not True:
            add("FULL_INTERMEDIATE_NOT_VERIFIED",route)
        if row.get("signed_proof_status")!="VERIFIED":
            add("ATOMIC_PROOF_NOT_VERIFIED",route)
        reasons=row.get("reason_codes",[])
        if not isinstance(reasons,list):
            raise ValueError("reason code inventory malformed")
        for reason in reasons:
            if not isinstance(reason,str):
                raise ValueError("non-string diagnostic reason")
            if reason=="CPMM_EFFECTIVE_FEE_OR_RESERVES_UNAVAILABLE":
                add("CPMM_EFFECTIVE_PRICING_BLOCKED",route)
            if reason in known:
                add(known[reason],route)
            if reason.startswith("ACCOUNT_DERIVED_QUOTE_BLOCKED:") or reason.startswith("ACCOUNT_PRICING_BLOCKED:"):
                add("ACCOUNT_SOURCE_QUOTE_BLOCKED",route)
        probes=row.get("observed_input_quote_probes",[])
        if not isinstance(probes,list):
            raise ValueError("observed quote probe inventory malformed")
        for probe in probes:
            if not isinstance(probe,dict):
                raise ValueError("invalid observed quote probe")
            if probe.get("status")!="INDICATIVE_OBSERVED_INPUT_COMPARISON":
                add("OBSERVED_INPUT_QUOTE_PROBE_BLOCKED",route)
        captured=row.get("captured_fee_and_compute")
        if not isinstance(captured,dict):
            add("CAPTURED_COST_EVIDENCE_MISSING",route)
        else:
            for fee in captured.get("fee_rows",[]):
                if fee.get("blocker")=="CPMM_CREATOR_FEE_PLACEMENT_UNVERIFIED":
                    add("CPMM_CREATOR_FEE_PLACEMENT_UNVERIFIED",route)
            if captured.get("positive_units_consumed") is None:
                add("SIGNED_COMPUTE_MISSING",route)
    issues={key:sorted(set(routes)) for key,routes in sorted(issues.items())}
    return {"status":"BLOCKERS_REMAIN_UNVERIFIED",
            "issue_routes":issues,"issue_counts":{k:len(v) for k,v in issues.items()},
            "total_routes":len(rows),"independently_validated_quote_samples":0,
            "profitability_confirmed":False,**SAFE}
