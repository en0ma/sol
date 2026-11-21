"""Meteora DLMM source-account-backed fee-envelope exact-input quotation.

This is a usable bounded economic primitive, not a guessed effective fee.
Both endpoints consume real decoded liquidity in directional bins at two
authenticated static/maximum-fee boundaries. Conservative minimum output
is only valid for the supplied bounded bin inventory and fee envelope; no
protocol-exact, executable, or profitability assertions are made.
"""
from arb.meteora_dlmm_source_bin_decoder import decode_from_fixture,directional_bins
from arb.meteora_dlmm_source_fee_decoder import fee_bounds_from_fixture,FEE_PRECISION
from arb.meteora_dlmm_bin_preflight import active_bin_array_index
from arb.meteora_dlmm_bin_quote import quote_bins
from arb.fixture_quote_execution_pipeline import extract_pool_states
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def quote_fee_envelope(fixture, *, pool, mint_in, amount_in, observed_unix,
                       maximum_arrays=3):
    if type(amount_in)is not int or not 0<amount_in<2**64:
        raise ValueError("positive DLMM integer input required")
    if type(maximum_arrays)is not int or not 1<=maximum_arrays<=3:
        raise ValueError("bounded DLMM array traversal required")
    rows=extract_pool_states(fixture)
    row=next((x for x in rows if x["venue"]=="meteora_dlmm"
              and x["address"]==pool),None)
    if row is None or any(fixture.get(k)is not False for k in SAFE):
        raise ValueError("source-owned DLMM pool fixture required")
    state=row["decoded_pool_state"]
    x=state["token_x_mint"];y=state["token_y_mint"]
    if mint_in not in (x,y):
        raise ValueError("DLMM source input mint mismatch")
    direction=mint_in==x
    active=state["active_id"]
    center=active_bin_array_index(active)
    indices=[center+(-i if direction else i) for i in range(maximum_arrays)]
    arrays=[]
    missing=[]
    for index in indices:
        try:
            arrays.append(decode_from_fixture(fixture,pool=pool,array_index=index))
        except ValueError as exc:
            missing.append({"array_index":index,"reason":str(exc)[:160]})
            if index==center:break
    if not arrays:
        return {"status":"SOURCE_NATIVE_DLMM_BIN_ARRAY_BLOCKED",
                "pool":pool,"source_slot":fixture["state_accounts_observed_slot"],
                "missing_arrays":missing,"protocol_exact_verified":False,**SAFE}
    selection=directional_bins(arrays,active_id=active,x_to_y=direction)
    bins=selection["bins"]
    rates=fee_bounds_from_fixture(fixture,pool=pool,observed_unix=observed_unix)
    outcomes=[]
    for name,rate in (("minimum_effective_fee",rates["minimum_total_fee_rate_numerator"]),
                      ("maximum_effective_fee",rates["maximum_total_fee_rate_numerator"])):
        try:
            priced=quote_bins(amount_in=amount_in,swap_x_for_y=direction,bins=bins,
                              total_fee_rate=rate,max_bins=70)
            outcomes.append({"fee_bound":name,"fee_rate_numerator":rate,
                             "amount_out":priced["amount_out"],
                             "fee_input_base_units":priced["fee_input_base_units"],
                             "bins_consumed":priced["bins_traversed"],
                             "complete_fill":True})
        except ValueError as exc:
            outcomes.append({"fee_bound":name,"fee_rate_numerator":rate,
                             "complete_fill":False,"blocker":str(exc)[:160]})
    # Actual LbPair volatility fields drive an independent integer
    # fee trajectory, rather than substituting a static guessed tier.
    from arb.meteora_dlmm_source_fee_decoder import dynamic_fee_rate_by_bin
    import base64
    pool_account=fixture["accounts"][pool]
    encoded=pool_account.get("data")
    if (not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64"):
        raise ValueError("source DLMM pool bytes missing for dynamic fee calculation")
    raw=base64.b64decode(encoded[0],validate=True)
    effective=None
    if bins:
        try:
            schedule=dynamic_fee_rate_by_bin(raw,bin_step=state["bin_step"],
                observed_unix=observed_unix,active_bin_id=active,
                visited_bin_ids=[b["bin_id"] for b in bins],
                swap_x_for_y=direction)
            enriched=[{**b,"effective_fee_rate":rate["effective_fee_rate"]}
                      for b,rate in zip(bins,schedule["rates"])]
            native=quote_bins(amount_in=amount_in,swap_x_for_y=direction,
                bins=enriched,total_fee_rate=rates["base_fee_rate_numerator"],max_bins=70)
            effective={"status":"SOURCE_VOLATILITY_DYNAMIC_FEE_MODELED",
                "amount_out":native["amount_out"],
                "fee_input_base_units":native["fee_input_base_units"],
                "fee_collect_mode":schedule["fee_collect_mode"],
                "bin_fee_rates":schedule["rates"],
                "source_clock":schedule["observed_unix"],
                "protocol_exact_verified":False,**SAFE}
        except ValueError as exc:
            effective={"status":"SOURCE_VOLATILITY_DYNAMIC_FEE_NOT_SUPPORTED",
                "reason":str(exc)[:180],"protocol_exact_verified":False,**SAFE}
    full=all(x["complete_fill"] for x in outcomes)
    result={"status":"SOURCE_NATIVE_DLMM_FEE_ENVELOPE_NOT_PROTOCOL_EXACT"
                       if full else "SOURCE_NATIVE_DLMM_ENVELOPE_CAPACITY_BLOCKED",
            "pool":pool,"input_mint":mint_in,
            "output_mint":y if direction else x,
            "input_base_units":amount_in,
            "source_slot":fixture["state_accounts_observed_slot"],
            "array_indices":[x["array_index"] for x in arrays],
            "decoded_bin_count":sum(x["bin_count"] for x in arrays),
            "walked_bin_count":len(bins),
            "missing_arrays":missing,
            "fee_bounds":outcomes,
            "source_derived_dynamic_fee_quote":effective,
            "fee_precision":FEE_PRECISION,
            "effective_fee_verified":False,
            "full_route_quoted":False,
            "protocol_exact_verified":False,
            "net_profit_verified":False,**SAFE}
    if full:
        result["lower_output_bound"]=min(x["amount_out"] for x in outcomes)
        result["upper_output_bound"]=max(x["amount_out"] for x in outcomes)
    return result
