"""Deterministic bounded missing tick-array intervals for authenticated pool captures.

No guessed liquidity: output is a request plan for missing source accounts.
"""
from arb.fixture_tick_coverage import coverage
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def missing_arrays(fixture,*,max_missing=128):
    if type(max_missing)is not int or not 1<=max_missing<=1024:
        raise ValueError("invalid maximum missing array count")
    report=coverage(fixture)
    from arb.fixture_quote_execution_pipeline import extract_pool_states
    states={r["address"]:r["decoded_pool_state"] for r in extract_pool_states(fixture)}
    result=[]
    for row in report["rows"]:
        span=(88 if row["venue"]=="orca" else 60)*states[row["pool"]]["tick_spacing"]
        entries=next(x for x in __import__("arb.fixture_concentrated_ticks",fromlist=["extract"]).extract(fixture)["pools"] if x["pool"]==row["pool"])
        starts=sorted(item["start_tick"] for item in entries["tick_arrays"])
        missing=[]
        for a,b in zip(starts,starts[1:]):
            if (b-a)%span:raise ValueError("misaligned array start gap")
            for start in range(a+span,b,span):
                missing.append(start)
                if len(missing)>max_missing:raise ValueError("too many missing contextual tick arrays")
        result.append({"venue":row["venue"],"pool":row["pool"],
          "current_array_captured":row["current_array_captured"],
          "missing_array_starts":missing,"missing_array_count":len(missing),
          "verified_directional_liquidity":False})
    return {"status":"MISSING_ARRAY_SOURCE_REQUEST_PLAN",
        "pools":result,"quote_accuracy_verified":False,**SAFE}
