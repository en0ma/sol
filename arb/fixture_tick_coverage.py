"""Detect missing intermediate tick array coverage without assuming empty liquidity.

Concentrated liquidity array decoding already exists. This module validates
contiguous directional array coverage and returns explicit gaps. It cannot
prove price parity or convert missing arrays into zero-liquidity bounds.
"""
from arb.fixture_concentrated_ticks import extract
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def coverage(fixture,*,max_arrays=24):
    report=extract(fixture,max_arrays=max_arrays)
    rows=[]
    for p in report["pools"]:
        width=88 if p["venue"]=="orca" else 60
        from arb.fixture_quote_execution_pipeline import extract_pool_states
        states=extract_pool_states(fixture)
        state=next(s["decoded_pool_state"] for s in states if s["address"]==p["pool"])
        spacing=state["tick_spacing"]
        span=width*spacing
        starts=sorted(a["start_tick"] for a in p["tick_arrays"])
        current=p["tick_current"]//span*span
        gaps=[missing for a,b in zip(starts,starts[1:]) for missing in range(a+span,b,span)]
        if len(gaps)>512:raise ValueError("too many missing tick arrays")
        rows.append({"venue":p["venue"],"pool":p["pool"],
           "captured_array_count":len(starts),
           "current_array_captured":current in starts,
           "missing_intermediate_array_starts":gaps,
           "contiguous_captured_arrays":bool(starts) and not gaps,
           "complete_directional_price_coverage_verified":False,**SAFE})
    return {"status":"CAPTURED_TICK_ARRAY_COVERAGE_DIAGNOSTIC",
       "rows":rows,"swap_output_parity_verified":False,**SAFE}
