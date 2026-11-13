"""Risk screen using observed signed outputs, explicit costs and quote error.

Never turn a diagnostic signed simulation into a market-ready opportunity.
"""
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
COSTS=("network_fee","priority_fee","compute_cost","slippage_buffer","quote_uncertainty_buffer")
def screen(*,input_units,observed_output_units,quoted_output_units,costs,slot_verified=False):
    if any(type(x)is not int or x<=0 for x in (input_units,observed_output_units,quoted_output_units)):
        raise ValueError("positive exact-input and output amounts required")
    if not isinstance(costs,dict) or set(costs)!=set(COSTS) or any(type(v)is not int or v<0 for v in costs.values()):
        raise ValueError("all nonnegative costs in start-mint base units required")
    deviation=abs(observed_output_units-quoted_output_units)*10000//quoted_output_units
    gross=observed_output_units-input_units
    cost=sum(costs.values())
    net=gross-cost
    return {"status":"OBSERVED_OFFLINE_RISK_DIAGNOSTIC",
        "observed_gross_start_mint_units":gross,
        "declared_cost_start_mint_units":cost,
        "observed_net_after_declared_costs_start_mint_units":net,
        "quote_deviation_bps":deviation,
        "positive_after_declared_costs":net>0,
        "snapshot_source_verified":slot_verified is True,
        "profitability_confirmed":False,
        "real_execution_failure_probability_verified":False,**SAFE}
