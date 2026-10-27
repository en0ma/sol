"""Independent four-to-six-hop signed handoff eligibility for M5.

A source capture is never itself a signed transaction or rollback receipt.
Only an independently accepted result from the existing universal coordinator
can satisfy execution evidence. Report blockers before any local simulation.
"""
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.source_snapshot_manifest import verify
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def assess(fixture,*,quote_report=None,signed_audit=None):
    verify(fixture)
    if fixture.get("fixture_kind")!="AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE":
        raise ValueError("authenticated four-to-six source fixture required")
    rows=extract_pool_states(fixture)
    if not 4<=len(rows)<=6:
        raise ValueError("four-to-six actual native source legs missing")
    if any(fixture.get(k) is not False for k in SAFE):
        raise ValueError("unsafe captured source route")
    issues=[]
    if (not isinstance(quote_report,dict) or
            quote_report.get("source_quote_verified") is not True or
            quote_report.get("protocol_exact_verified") is not True or
            quote_report.get("snapshot_slot")!=fixture["state_accounts_observed_slot"] or
            quote_report.get("hops")!=len(rows)):
        issues.append("same-slot protocol-exact native route quotes missing")
    # The existing three-leg coordinator receipts cannot be reused as an
    # independent signed four-hop acceptance result.
    if (not isinstance(signed_audit,dict) or
            signed_audit.get("status")!="VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK" or
            signed_audit.get("signed_atomic_simulation_verified") is not True or
            signed_audit.get("rollback_failure_case_verified") is not True or
            signed_audit.get("route_pool_addresses")!=fixture["route_pool_addresses"] or
            signed_audit.get("snapshot_slot")!=fixture["state_accounts_observed_slot"]):
        issues.append("independent four-to-six-hop signed CPI/SPL and rollback receipt missing")
    # Execution should NOT be classified accepted by an arbitrary flags-only
    # object; until an independent 4–6-hop auditor is wired, always block.
    issues.append("independent four-to-six-hop acceptance auditor not yet integrated")
    return {"status":"FOUR_TO_SIX_HOP_SIGNED_HANDOFF_BLOCKED",
            "hops":len(rows),"source_slot":fixture["state_accounts_observed_slot"],
            "route_venues":[r["venue"] for r in rows],
            "blockers":issues,"independently_signed_verified":False,
            "net_profit_verified":False,**SAFE}
