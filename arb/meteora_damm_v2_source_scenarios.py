"""Source-authenticated DAMM v2 fee and reserve scenario pricing.

The pool's fee scheduler/mode is not attested by vault balances; therefore
enumerate only bounded modeled scenarios, never fabricate an effective rate.
Authentic pool mint, same-slot classic SPL reserves and pool state are required.
"""
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_pool_fundamentals import extract
from arb.meteora_damm_v2_quote import quote_collection_mode
from arb.meteora_damm_v2_native_fee_math import quote_native_fee,FEE_DENOMINATOR
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def scenario_envelope(fixture,*,pool,mint_in,amount_in,
                      fee_rates_ppm=(0,100,1000,10000,100000)):
    if (type(amount_in)is not int or not 0<amount_in<2**64 or
            any(fixture.get(k)is not False for k in SAFE)):
        raise ValueError("safe source amount required")
    if (not isinstance(fee_rates_ppm,(list,tuple)) or not 2<=len(fee_rates_ppm)<=12
            or sorted(set(fee_rates_ppm))!=list(fee_rates_ppm)
            or any(type(v)is not int or not 0<=v<1000000 for v in fee_rates_ppm)):
        raise ValueError("bounded explicitly hypothetical fee scenarios required")
    rows=extract_pool_states(fixture)
    row=next((r for r in rows if r["venue"]=="meteora_damm_v2"
              and r["address"]==pool),None)
    if row is None:raise ValueError("DAMM v2 source pool missing")
    state=row["decoded_pool_state"]
    if state["pool_status"]!=0 or state["token_a_flag"] or state["token_b_flag"]:
        raise ValueError("DAMM source pool inactive or unsupported token extensions")
    mint_a,mint_b=state["token_a_mint"],state["token_b_mint"]
    if mint_in not in (mint_a,mint_b):raise ValueError("DAMM input mint mismatch")
    fund=next((f for f in extract(fixture)["fundamentals"] if f["address"]==pool),None)
    if fund is None:raise ValueError("missing native source SPL vaults")
    reserve_a,reserve_b=fund["vault_base_units"]
    inputs_a=mint_in==mint_a
    outcomes=[]
    for rate in fee_rates_ppm:
        for mode in ("BASE_AND_QUOTE","QUOTE_ONLY","QUOTE_COMPOUNDING"):
            try:
                q=quote_native_fee(reserve_a=reserve_a,reserve_b=reserve_b,
                                   amount_in=amount_in,input_is_a=inputs_a,
                                   total_fee_numerator=rate*1000,
                                   collection_mode=mode,
                                   fee_version=1)
            except ValueError:
                continue
            outcomes.append({"hypothetical_fee_ppm":rate,
                             "hypothetical_collection_mode":mode,
                             "amount_out":q["amount_out"],
                             "native_fee_numerator":rate*1000,
                             "native_fee_denominator":FEE_DENOMINATOR,
                             "fee_input_units":q["fee_input_units"],
                             "fee_output_units":q["fee_output_units"]})
    if not outcomes:raise ValueError("DAMM model scenarios cannot fill input")
    return {"status":"DAMM_V2_SOURCE_RESERVE_HYPOTHETICAL_FEE_ENVELOPE",
            "pool":pool,"source_slot":fixture["state_accounts_observed_slot"],
            "input_mint":mint_in,"output_mint":mint_b if inputs_a else mint_a,
            "input_base_units":amount_in,"vault_reserves":[reserve_a,reserve_b],
            "scenarios":outcomes,
            "lower_modeled_output":min(x["amount_out"] for x in outcomes),
            "upper_modeled_output":max(x["amount_out"] for x in outcomes),
            "effective_fee_verified":False,"curve_model_verified":False,
            "protocol_exact_verified":False,**SAFE}
