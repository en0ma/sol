"""Read-only pre-simulation economics and quote evidence requirements.

Explicit missing evidence is always non-actionable. No unobserved lamport charge
or price conversion is inserted based on compute units or route profitability.
"""
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def gate(fixture,receipt,parity,economics):
    venues=fixture.get("route_venues",[])
    if (len(venues)!=3 or len(set(venues))!=3 or
            receipt.get("signed_atomic_simulation_verified") is not True or
            receipt.get("rollback_failure_case_verified") is not True):
        return {"status":"SIGNED_COVERAGE_NOT_ACCEPTED","blockers":["SIGNED_CPI_OR_ROLLBACK_UNPROVEN"],**SAFE}
    blockers=[]
    comparisons=parity.get("leg_comparisons",[]) if isinstance(parity,dict) else []
    if len(comparisons)!=3:
        blockers.append("THREE_LEG_SOURCE_QUOTE_COVERAGE_INCOMPLETE")
    for i,venue in enumerate(venues):
        if i>=len(comparisons):
            blockers.append("LEG_%d_QUOTE_NOT_COMPUTED"%i)
            continue
        leg=comparisons[i]
        if leg.get("quoted_output_base_units") is None:
            blockers.append("LEG_%d_%s_SOURCE_PRICE_UNAVAILABLE"%(i,venue.upper()))
        if leg.get("quote_verified") is not True:
            blockers.append("LEG_%d_INDEPENDENT_QUOTE_PARITY_UNVERIFIED"%i)
    if economics.get("fee_source_verified") is not True:
        blockers.append("OBSERVED_TRANSACTION_FEE_UNVERIFIED")
    if economics.get("conversion_authenticated") is not True:
        blockers.append("START_MINT_CONVERSION_UNVERIFIED")
    if economics.get("profitability_verified") is not True:
        blockers.append("NET_PROFITABILITY_UNVERIFIED")
    return {"status":"RESEARCH_EVIDENCE_INCOMPLETE" if blockers else "RESEARCH_EVIDENCE_COMPLETE",
            "blockers":blockers,"signed_venue_triple":venues,
            "observed_compute_units":receipt.get("positive_units_consumed"),
            "gross_start_mint_delta":economics.get("gross_delta_start_mint_base_units"),
            "net_start_mint_delta":economics.get("net_delta_start_mint_base_units"),**SAFE}
