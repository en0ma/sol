"""Conservative signed offline realized-PnL sensitivity, without live claims."""
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def sensitivity(*,input_units,observed_output_units,declared_cost_units,extra_uncertainty_bps):
    if any(type(x)is not int or x<0 for x in (input_units,observed_output_units,declared_cost_units,extra_uncertainty_bps)) or input_units==0 or extra_uncertainty_bps>10000:
        raise ValueError("invalid bounded start-mint risk inputs")
    # Apply additional adverse slippage to output, rather than to hypothetical profit.
    downside=(observed_output_units*extra_uncertainty_bps+9999)//10000
    conservative=observed_output_units-downside-input_units-declared_cost_units
    return {"status":"OFFLINE_DOWNSIDE_SCENARIO",
       "additional_adverse_output_units":downside,
       "conservative_net_start_mint_units":conservative,
       "positive_under_downside_scenario":conservative>0,
       "execution_failure_risk_empirically_verified":False,
       "profitability_confirmed":False,**SAFE}
