"""Compare indicative CLMM estimates with authenticated signed simulation deltas.

No observed execution makes an indicative quote executable. Never treat a
positive difference or single-swap quote as arbitrage profit.
"""
def compare(quote,simulation):
    if (not isinstance(quote,dict) or
            quote.get("status")!="INDICATIVE_WITHIN_TICK_ONLY" or
            quote.get("actionable") is not False or
            not isinstance(simulation,dict) or
            simulation.get("simulation_verified") is not True):
        raise ValueError("unverified CLMM quote comparison provenance")
    estimate=quote.get("estimated_output_base_units")
    observed=simulation.get("received_base_units")
    if (type(estimate)is not int or type(observed)is not int or
            estimate<=0 or observed<=0):
        raise ValueError("invalid CLMM quote comparison amounts")
    difference=observed-estimate
    return {"status":"SIGNED_SINGLE_SWAP_QUOTE_RECONCILED",
            "estimated_output_base_units":estimate,
            "observed_output_base_units":observed,
            "observed_minus_estimated_base_units":difference,
            "absolute_error_bps_of_observed":(abs(difference)*10000+observed-1)//observed,
            "quote_matches_observed_exactly":difference==0,
            "actionable":False,"atomic_cycle_simulated":False,
            "profitable_arbitrage_verified":False}
