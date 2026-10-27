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
    outcomes=[]
    for index,observation in enumerate(observations):
        row=rows[index]
        if (not isinstance(observation,dict) or
                observation.get("index")!=index or
                observation.get("venue")!=row["venue"] or
                observation.get("pool")!=row["address"] or
                observation.get("amount_in")!=planned[index] or
                observation.get("observed_output")!=planned[index+1]):
            raise ValueError("signed prefix SPL output or venue identity mismatch")
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
        elif status in ("NATIVE_QUOTE_MODELED_NOT_EXACT",
                         "NATIVE_QUOTE_BOUNDED_NOT_EXACT"):
            classification="FEE_SCENARIO_NOT_COMPARABLE_AS_PROTOCOL_EXACT"
        if source_output is not None and (
                type(source_output)is not int or not 0<source_output<2**64):
            raise ValueError("invalid independently source-derived amount")
        signed=observation["observed_output"]
        delta=source_output-signed if source_output is not None else None
        outcomes.append({"leg_index":index,"venue":row["venue"],"pool":row["address"],
            "source_slot":fixture["state_accounts_observed_slot"],
            "exact_input_base_units":planned[index],
            "signed_prefix_output_base_units":signed,
            "source_native_modeled_output_base_units":source_output,
            "modeled_minus_signed_base_units":delta,
            "absolute_model_error_base_units":abs(delta) if delta is not None else None,
            "native_quote_status":status,"classification":classification,
            "signed_prefix_observation_authenticated":True,
            "protocol_exact_parity_verified":False,**SAFE})
    return {"status":"SOURCE_NATIVE_TO_SIGNED_PREFIX_COMPARISON",
        "hops":n,"compared_prefix_count":len(outcomes),
        "numeric_comparison_count":sum(r["modeled_minus_signed_base_units"] is not None
                                       for r in outcomes),
        "source_slot":fixture["state_accounts_observed_slot"],
        "comparisons":outcomes,
        "quote_accuracy_verified":False,
        "atomic_execution_independently_accepted":False,
        "net_profit_verified":False,**SAFE}
