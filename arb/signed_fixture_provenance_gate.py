"""Fail-closed identity and provenance audit for fixture vs signed Surfpool receipt.

This is a prerequisite to measured quote accuracy, NOT accuracy proof.
Never synthesize an execution slot from the fixture capture slot.
"""
from arb.source_snapshot_manifest import verify
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def audit(fixture,receipt,*,quoted_first_input=None):
    verify(fixture)
    reasons=[]
    if not isinstance(receipt,dict):
        return {"status":"UNVERIFIED","reasons":["signed receipt missing"],**SAFE}
    expected_pools=[fixture.get("first_pool"),fixture.get("second_pool")]
    expected_mints=fixture.get("route_mints")
    if receipt.get("route_pool_addresses")!=expected_pools:
        reasons.append("signed receipt route pool mismatch")
    if receipt.get("route_mints")!=expected_mints:
        reasons.append("signed receipt route mint mismatch")
    if receipt.get("state_account_manifest_sha256")!=fixture.get("state_account_manifest_sha256"):
        reasons.append("signed receipt source account checksum missing/mismatch")
    captured=fixture.get("state_accounts_observed_slot")
    if receipt.get("state_accounts_observed_slot")!=captured:
        reasons.append("signed receipt captured state slot missing/mismatch")
    readback=receipt.get("hydrated_fork_state_readback")
    if not isinstance(readback,dict) or readback.get("status")!="HYDRATED_FORK_ACCOUNT_BYTES_MATCH":
        reasons.append("hydrated fork readback evidence missing")
    elif (readback.get("captured_source_slot")!=captured or
          type(readback.get("accounts_checked"))is not int or
          not 0<readback["accounts_checked"]<=fixture.get("state_account_count",0) or
          type(readback.get("fork_readback_slot"))is not int or
          readback.get("source_mainnet_slot_independently_attested") is not False):
        reasons.append("hydrated fork readback metadata inconsistent")
    if receipt.get("source_snapshot_slot")!=captured or type(captured)is not int:
        reasons.append("signed receipt execution source slot unauthenticated")
    if type(quoted_first_input)is not int or quoted_first_input<=0:
        reasons.append("quoted first leg input missing")
    else:
        initial=receipt.get("initial_balances_base_units")
        final=receipt.get("positive_post_balances_base_units")
        if (not isinstance(initial,list) or not isinstance(final,list)
                or len(initial)!=3 or len(final)!=3 or
                any(type(x)is not int or x<0 for x in initial+final)):
            reasons.append("signed SPL before and after balances missing")
        elif initial[0]-final[0]!=quoted_first_input:
            reasons.append("signed SPL first leg input differs from quote")
    return {"status":"PROVENANCE_FIELDS_CONSISTENT_NOT_INDEPENDENTLY_ATTESTED" if not reasons else "UNVERIFIED",
        "reasons":reasons,"fixture_slot":captured,
        "same_fork_state_independently_attested":False,
        "signed_quote_accuracy_verified":False,**SAFE}
