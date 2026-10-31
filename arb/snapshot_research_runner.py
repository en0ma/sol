"""Connect trusted offline pool snapshots to the unified M5 research pipeline.

Deliberately requires an independently provided same-start-mint cost estimator.
Does not fetch live accounts, invent fee conversions, or submit transactions.
"""
from arb.authenticated_quote_provider import from_snapshot
from arb.research_engine_pipeline import run_cycle_pipeline

def run_authenticated_snapshot(snapshot,*,as_of_unix,initial_input,
                              cost_provider,simulate_provider=None,
                              max_age=60,max_slot_skew=32):
    if type(initial_input)is not int or not 0<initial_input<2**64:
        raise ValueError("positive exact-input amount required")
    quote,registry=from_snapshot(snapshot,now=as_of_unix,max_age=max_age,
                                 max_slot_skew=max_slot_skew)
    # Only independently accepted, same-batch entries enter topology search.
    outcome=run_cycle_pipeline(
        registry["pools"],now=as_of_unix,initial_input=initial_input,
        quote_provider=quote,cost_provider=cost_provider,
        simulate_provider=simulate_provider,max_age=max_age)
    return {**outcome,"snapshot_rejected_pools":registry["rejections"],
            "authenticated_snapshot_pool_count":registry["pool_count"],
            "real_rpc_snapshot_loaded":False,
            "market_quotes_are_indicative":True}
