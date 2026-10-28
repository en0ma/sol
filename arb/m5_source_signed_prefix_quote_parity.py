"""Compare authenticated venue-native prices against independently signed prefix SPL observations.

Uses the same single-slot source manifest and exact prefix input amount for
each venue, preserving both numerical differences and unresolved fee regimes.
A signed prefix output isn't an atomic end-to-end acceptance, and a modeled
fee scenario is not a protocol-exact quote. This reconciliation deliberately
keeps quote_accuracy_verified false until executable parity is established.
"""
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_all_venue_signed_quotes import quote_leg
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def compare(fixture,receipt,*,observed_unix):
    if (not isinstance(receipt,dict) or
            any(receipt.get(key)is not False for key in SAFE) or
            any(fixture.get(key)is not False for key in SAFE)):
        raise ValueError("nonbroadcast source and signed observation required")
    rows=extract_pool_states(fixture)
    n=len(rows)
    planned=receipt.get("planned_inputs")
    observations=receipt.get("signed_prefix_observations")
    if (not 2<=n<=6 or not isinstance(planned,list) or len(planned)!=n
            or not isinstance(observations,list) or len(observations)!=n-1
            or receipt.get("state_accounts_observed_slot")!=fixture["state_accounts_observed_slot"]
            or receipt.get("state_account_manifest_sha256")!=fixture["state_account_manifest_sha256"]
            or receipt.get("route_pool_addresses")!=fixture["route_pool_addresses"]
            or receipt.get("route_mints")!=fixture["route_mints"]):
        raise ValueError("source-slot or signed prefix identities do not reconcile")
    if any(type(x)is not int or not 0<x<2**64 for x in planned):
        raise ValueError("source signed input amounts invalid")
    # Check the complete independent signed prefix trace BEFORE calling any
    # venue quote adapter. A forged later SPL amount may otherwise be hidden
    # by an unrelated earlier native pricing dependency or missing fee state.
    for index,observation in enumerate(observations):
        row=rows[index]
        if (not isinstance(observation,dict) or
                observation.get("index")!=index or
                observation.get("venue")!=row["venue"] or
                observation.get("pool")!=row["address"] or
                observation.get("amount_in")!=planned[index] or
                observation.get("observed_output")!=planned[index+1]):
            raise ValueError("signed prefix SPL output or venue identity mismatch")
    # Only an independently simulated complete atomic receipt can supply
    # the terminal swap output. Signed prefixes alone never authenticate
    # the final output or an end-to-end route's realized starting-mint delta.
    post=receipt.get("positive_post_balances_base_units")
    before=receipt.get("initial_balances_base_units")
    complete=(receipt.get("status")=="SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED"
              and receipt.get("signed_atomic_simulation_verified") is True
              and receipt.get("signed_cpi_per_leg_verified") is True
              and receipt.get("rollback_failure_case_verified") is True)
    terminal=None
    independent_accepted=False
    if complete:
        # A claimed success flag and terminal SPL balance are not an
        # authenticated transaction. For a source-captured 4–6-hop route,
        # require the independent account-byte/CPI/rollback AND signed wire
        # verifier before interpreting the final post-balance as observed.
        if fixture.get("fixture_kind")!="AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE":
            raise ValueError("signed atomic terminal requires authenticated four-to-six-hop source fixture")
        from arb.m5_four_to_six_source_signed_acceptance import assess
        verdict=assess(fixture,receipt)
        if verdict.get("status")!="VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK":
            raise ValueError("signed terminal independent source/CPI/cryptographic audit failed")
        independent_accepted=True
        if (not isinstance(post,list) or not isinstance(before,list)
                or len(post)!=n+1 or len(before)!=n+1
                or before!=[planned[0]]+[0]*n
                or any(type(x)is not int or x!=0 for x in post[:-1])
                or type(post[-1])is not int or not 0<post[-1]<2**64):
            raise ValueError("independent complete signed atomic SPL final balances invalid")
        terminal=post[-1]-before[-1]
    signed_outputs=[o["observed_output"] for o in observations]
    if terminal is not None:signed_outputs.append(terminal)
    outcomes=[]
    for index,signed in enumerate(signed_outputs):
        row=rows[index]
        native=quote_leg(fixture,leg_index=index,amount_in=planned[index],
                         observed_unix=observed_unix)
        if (not isinstance(native,dict) or
                any(native.get(k)is not False for k in SAFE) or
                native.get("source_slot")!=fixture["state_accounts_observed_slot"] or
                native.get("venue")!=row["venue"] or
                native.get("pool")!=row["address"]):
            raise ValueError("unsafe or unrelated source-native quote")
        status=native.get("quote_status")
        source_output=None
        classification="UNRESOLVED_NATIVE_QUOTE"
        if status=="SOURCE_BOUND_INDICATIVE":
            source_output=native.get("predicted_output_base_units")
            classification="INDICATIVE_VERSUS_SIGNED"
        elif status=="NATIVE_QUOTE_SOURCE_DERIVED_NOT_EXACT":
            envelope=native.get("native_fee_envelope")
            if isinstance(envelope,dict):
                dynamic=envelope.get("source_derived_dynamic_fee_quote")
                source_output=dynamic.get("amount_out") if isinstance(dynamic,dict) else None
            classification="NATIVE_DYNAMIC_FEE_MODEL_VERSUS_SIGNED"
        elif status in ("NATIVE_QUOTE_SELECTED_FEE_MODE_NOT_EXACT",
                         "NATIVE_QUOTE_SOURCE_BASE_FEE_NOT_EXACT"):
            envelope=native.get("native_fee_envelope")
            if (not isinstance(envelope,dict) or
                    envelope.get("source_slot")!=fixture["state_accounts_observed_slot"]
                    or any(envelope.get(k)is not False for k in SAFE)):
                raise ValueError("signed parity source-selected account mismatch")
            if status=="NATIVE_QUOTE_SELECTED_FEE_MODE_NOT_EXACT":
                if (row["venue"]!="pumpswap" or
                        envelope.get("fee_mode_selected_from_source") is not True
                        or len(envelope.get("candidates",[]))!=1):
                    raise ValueError("signed PumpSwap selected source tier missing")
                source_output=envelope["candidates"][0].get("amount_out")
                classification="SELECTED_SOURCE_PUMP_FEE_MODEL_VERSUS_SIGNED"
            else:
                state=envelope.get("source_pool_fee_schedule")
                if (row["venue"]!="meteora_damm_v2"
                        or not isinstance(state,dict)
                        or state.get("dynamic_fee_initialized") is not False
                        or state.get("source_slot")!=fixture["state_accounts_observed_slot"]):
                    raise ValueError("signed DAMM source base fee mismatch")
                source_output=state.get("amount_out_before_dynamic_fee")
                classification="SOURCE_DAMM_BASE_FEE_MODEL_VERSUS_SIGNED"
        elif status in ("NATIVE_QUOTE_MODELED_NOT_EXACT",
                         "NATIVE_QUOTE_BOUNDED_NOT_EXACT"):
            classification="FEE_SCENARIO_NOT_COMPARABLE_AS_PROTOCOL_EXACT"
        if source_output is not None and (
                type(source_output)is not int or not 0<source_output<2**64):
            raise ValueError("invalid independently source-derived amount")
        source_fee_mode_scenarios=[]
        if row["venue"]=="raydium_clmm" and native.get(
                "source_fee_evidence",{}).get("fee_on_input") is True:
            alternate=quote_leg(fixture,leg_index=index,
                amount_in=planned[index],observed_unix=observed_unix,
                clmm_fee_on_input=False)
            if (not isinstance(alternate,dict) or
                    any(alternate.get(k)is not False for k in SAFE) or
                    alternate.get("venue")!=row["venue"] or
                    alternate.get("pool")!=row["address"] or
                    alternate.get("source_slot")!=fixture["state_accounts_observed_slot"]):
                raise ValueError("CLMM alternate source fee mode identity mismatch")
            alt_amount=alternate.get("predicted_output_base_units")
            if (alternate.get("quote_status")=="SOURCE_BOUND_FEE_MODE_SCENARIO_NOT_EXACT"
                    and type(alt_amount)is int and 0<alt_amount<2**64):
                source_fee_mode_scenarios.append({
                    "scenario":"OUTPUT_FEE_COLLECTION_UNATTESTED",
                    "amount_out":alt_amount,
                    "modeled_minus_signed_base_units":alt_amount-signed,
                    "protocol_exact_parity_verified":False,**SAFE})
        delta=source_output-signed if source_output is not None else None
        outcomes.append({"leg_index":index,"venue":row["venue"],"pool":row["address"],
            "source_slot":fixture["state_accounts_observed_slot"],
            "exact_input_base_units":planned[index],
            "signed_observed_output_base_units":signed,
            "signed_observation_type":"ATOMIC_TERMINAL_POST_ACCOUNT" if index==n-1
                                      else "SIGNED_CUMULATIVE_PREFIX",
            "source_native_modeled_output_base_units":source_output,
            "modeled_minus_signed_base_units":delta,
            "absolute_model_error_base_units":abs(delta) if delta is not None else None,
            "native_quote_status":status,"classification":classification,
            "alternate_source_fee_mode_scenarios":source_fee_mode_scenarios,
            "signed_prefix_observation_authenticated":index<n-1,
            "signed_atomic_terminal_post_account_authenticated":index==n-1,
            "protocol_exact_parity_verified":False,**SAFE})
    return {"status":"SOURCE_NATIVE_TO_SIGNED_ALL_LEGS_COMPARISON" if terminal is not None
                     else "SOURCE_NATIVE_TO_SIGNED_PREFIX_COMPARISON",
        "hops":n,"compared_prefix_count":len(observations),
        "compared_signed_legs":len(outcomes),
        "atomic_terminal_observation_used":terminal is not None,
        "signed_atomic_terminal_output_base_units":terminal,
        "signed_atomic_gross_delta_start_mint_base_units":
            terminal-planned[0] if terminal is not None else None,
        "clmm_alternate_fee_mode_comparison_count":sum(
            len(r["alternate_source_fee_mode_scenarios"]) for r in outcomes),
        "numeric_comparison_count":sum(r["modeled_minus_signed_base_units"] is not None
                                       for r in outcomes),
        "source_slot":fixture["state_accounts_observed_slot"],
        "comparisons":outcomes,
        "quote_accuracy_verified":False,
        "atomic_execution_independently_accepted":independent_accepted,
        "net_profit_verified":False,**SAFE}

def main():
    import argparse,json
    from pathlib import Path
    p=argparse.ArgumentParser()
    p.add_argument("--fixture",required=True)
    p.add_argument("--receipt",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--observed-unix",type=int,required=True)
    args=p.parse_args()
    output=Path(args.output)
    try:
        result=compare(json.loads(Path(args.fixture).read_text()),
            json.loads(Path(args.receipt).read_text()),
            observed_unix=args.observed_unix)
    except (ValueError,TypeError,KeyError,RuntimeError,OverflowError) as exc:
        result={"status":"SOURCE_SIGNED_NATIVE_PARITY_BLOCKED",
                "reason":str(exc)[:240],"quote_accuracy_verified":False,
                "net_profit_verified":False,**SAFE}
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":result["status"],
        "compared_prefix_count":result.get("compared_prefix_count",0),
        "quote_accuracy_verified":False,**SAFE}))
if __name__=="__main__":main()
