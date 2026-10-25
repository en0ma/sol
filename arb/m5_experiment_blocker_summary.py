"""Fail-closed prioritization of actual signed amount and quote blockers."""
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def summarize(rows):
    if not isinstance(rows,list):
        raise ValueError("diagnostic rows required")
    issues={}
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
        for reason in row.get("reason_codes",[]):
            if reason=="CPMM_EFFECTIVE_FEE_OR_RESERVES_UNAVAILABLE":
                add("CPMM_EFFECTIVE_PRICING_BLOCKED",route)
        captured=row.get("captured_fee_and_compute")
        if not isinstance(captured,dict):
            add("CAPTURED_COST_EVIDENCE_MISSING",route)
        else:
            for fee in captured.get("fee_rows",[]):
                if fee.get("blocker")=="CPMM_CREATOR_FEE_PLACEMENT_UNVERIFIED":
                    add("CPMM_CREATOR_FEE_PLACEMENT_UNVERIFIED",route)
            if captured.get("positive_units_consumed") is None:
                add("SIGNED_COMPUTE_MISSING",route)
    return {"status":"BLOCKERS_REMAIN_UNVERIFIED",
            "issue_routes":issues,"issue_counts":{k:len(v) for k,v in issues.items()},
            "total_routes":len(rows),"independently_validated_quote_samples":0,
            "profitability_confirmed":False,**SAFE}
