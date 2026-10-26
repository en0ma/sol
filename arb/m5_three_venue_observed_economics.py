"""Exact integer observed research economics; never infer SOL fees from CU alone.

Only a genuine signed closed-route receipt and explicitly documented fee
observations may be analyzed. Price conversion is a supplied research datum,
not an authenticated on-chain oracle. Missing fee/conversion evidence blocks
net profitability. Everything remains simulation-only.
"""
from arb.m5_three_distinct_venue_signed_acceptance import verify as accept
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
LAMPORTS_PER_SOL=1_000_000_000
WRAPPED_SOL_MINT="So11111111111111111111111111111111111111112"

def evaluate(fixture,receipt,*,observed_fee_lamports=None,
             start_mint_base_units_per_sol=None,conversion_authenticated=False,
             downside_bps=(0,50,100,250),
             fee_observation=None):
    report={"status":"COST_EVIDENCE_BLOCKED","gross_output_base_units":None,
            "gross_delta_start_mint_base_units":None,
            "net_delta_start_mint_base_units":None,"fee_start_mint_base_units":None,
            "fee_source_verified":False,"conversion_authenticated":False,
            "downside_scenarios":[],"profitability_verified":False,**SAFE}
    try:
        accept(fixture,receipt)
    except (ValueError,TypeError,KeyError) as exc:
        report["reason"]="SIGNED_RECEIPT_UNVERIFIED: "+str(exc)[:140]
        return report
    before=receipt.get("initial_balances_base_units")
    after=receipt.get("positive_post_balances_base_units")
    spent=receipt.get("planned_inputs")
    if (not isinstance(before,list) or not isinstance(after,list)
            or len(before)!=len(after)!=4 or
            any(type(x)is not int or x<0 for x in before+after)
            or not isinstance(spent,list) or len(spent)!=3
            or any(type(x)is not int or x<=0 for x in spent)
            or before[0]-after[0]!=spent[0]):
        report["reason"]="SIGNED_START_AND_TERMINAL_SPL_AMOUNTS_MISSING"
        return report
    output=after[3]-before[3]
    if output<=0:
        report["reason"]="POSITIVE_TERMINAL_OUTPUT_MISSING"
        return report
    report["observed_positive_compute_units"]=receipt.get("positive_units_consumed")
    estimate=receipt.get("signed_message_fee_estimate")
    if isinstance(estimate,dict) and estimate.get("status")=="SIGNED_MESSAGE_FEE_ESTIMATE_ONLY":
        fee=estimate.get("estimated_fee_lamports")
        if type(fee)is int and fee>=0:
            report["exact_signed_message_fee_estimate_lamports"]=fee
            report["exact_signed_message_fee_sha256"]=estimate.get("signed_message_sha256")
            report["estimated_fee_paid"]=False
    report["gross_output_base_units"]=output
    report["gross_delta_start_mint_base_units"]=output-spent[0]
    # Break-even is an observable upper bound on *total* fees/slippage
    # denominated in the starting mint, NOT an assumption about paid fees.
    report["maximum_affordable_total_cost_start_mint_base_units"]=max(0,output-spent[0])
    report["minimum_output_to_break_even_without_fees_base_units"]=spent[0]
    report["gross_return_bps"]=(output-spent[0])*10_000//spent[0]
    if (not isinstance(downside_bps,(list,tuple)) or
            any(type(n)is not int or not 0<=n<=10_000 for n in downside_bps)):
        raise ValueError("invalid downside scenarios")
    # Gross signed downside is measurable without pretending offline fees
    # were paid; net scenario fields require both independent fee and FX proof.
    report["downside_scenarios"]=[{"output_haircut_bps":n,
        "gross_delta_start_mint_base_units":output*(10_000-n)//10_000-spent[0],
        "maximum_affordable_total_cost_start_mint_base_units":max(0,output*(10_000-n)//10_000-spent[0]),
        "net_delta_start_mint_base_units":None} for n in downside_bps]
    if fee_observation is not None:
        if (not isinstance(fee_observation,dict)
                or fee_observation.get("kind")!="INDEPENDENT_OBSERVED_TRANSACTION_FEE"
                or fee_observation.get("source")!="getTransaction"
                or type(fee_observation.get("lamports")) is not int
                or fee_observation["lamports"]<0
                or not isinstance(fee_observation.get("signature_or_message_hash"),str)
                or not fee_observation["signature_or_message_hash"]):
            report["reason"]="INDEPENDENT_FEE_OBSERVATION_INVALID"
            return report
        if (observed_fee_lamports is not None
                and observed_fee_lamports!=fee_observation["lamports"]):
            report["reason"]="INDEPENDENT_FEE_OBSERVATION_CONFLICT"
            return report
        # A getTransaction fee is only attributable if the signed execution
        # receipt itself carries that exact transaction signature. Offline
        # simulateTransaction has no settled signature; this must fail closed.
        if (receipt.get("settled_transaction_signature") !=
                fee_observation["signature_or_message_hash"]):
            report["reason"]="SETTLED_TRANSACTION_SIGNATURE_NOT_MATCHED"
            return report
        observed_fee_lamports=fee_observation["lamports"]
        report["observed_fee_provenance"]=dict(fee_observation)
    if (type(observed_fee_lamports)is not int or observed_fee_lamports<0):
        report["reason"]="OBSERVED_TRANSACTION_FEE_LAMPORTS_MISSING"
        return report
    report["observed_fee_lamports"]=observed_fee_lamports
    # Fee amount must come from a separate observed fee receipt. CU is *not*
    # a fee, and simulated atomic logs alone do not prove fee assessment.
    start_mint=fixture.get("route_mints",[None])[0]
    if start_mint==WRAPPED_SOL_MINT:
        # Native wrapped SOL SPL base units are lamports by token definition.
        # This is a deterministic denomination equivalence, not a market FX oracle.
        if (start_mint_base_units_per_sol not in (None,LAMPORTS_PER_SOL)
                or conversion_authenticated is False and start_mint_base_units_per_sol is not None):
            report["reason"]="WRAPPED_SOL_CONVERSION_CONTRADICTS_MINT_DENOMINATION"
            return report
        start_mint_base_units_per_sol=LAMPORTS_PER_SOL
        conversion_authenticated=True
        report["conversion_basis"]="WRAPPED_SOL_LAMPORT_DENOMINATION"
    if (type(start_mint_base_units_per_sol)is not int or
            start_mint_base_units_per_sol<=0 or conversion_authenticated is not True):
        report["reason"]="START_MINT_SOL_CONVERSION_NOT_AUTHENTICATED"
        return report
    fee=(observed_fee_lamports*start_mint_base_units_per_sol+
         LAMPORTS_PER_SOL-1)//LAMPORTS_PER_SOL
    report["fee_start_mint_base_units"]=fee
    report["fee_source_verified"]=fee_observation is not None
    report["conversion_authenticated"]=True
    report["net_delta_start_mint_base_units"]=output-spent[0]-fee
    report["downside_scenarios"]=[{**scenario,
        "net_delta_start_mint_base_units":scenario["gross_delta_start_mint_base_units"]-fee}
        for scenario in report["downside_scenarios"]]
    report["status"]=("COST_OBSERVATIONS_ACCOUNTED_SIMULATION_ONLY"
                      if fee_observation is not None else
                      "COST_SCENARIO_WITH_UNVERIFIED_FEE_INPUT")
    # Fee claims and pricing input provenance are not independent economic
    # verification even when manually supplied; never approve a trade.
    return report
