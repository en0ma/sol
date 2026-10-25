"""Exact integer observed research economics; never infer SOL fees from CU alone.

Only a genuine signed closed-route receipt and explicitly documented fee
observations may be analyzed. Price conversion is a supplied research datum,
not an authenticated on-chain oracle. Missing fee/conversion evidence blocks
net profitability. Everything remains simulation-only.
"""
from arb.m5_three_distinct_venue_signed_acceptance import verify as accept
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
LAMPORTS_PER_SOL=1_000_000_000

def evaluate(fixture,receipt,*,observed_fee_lamports=None,
             start_mint_base_units_per_sol=None,conversion_authenticated=False,
             downside_bps=(0,50,100,250)):
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
    report["gross_output_base_units"]=output
    report["gross_delta_start_mint_base_units"]=output-spent[0]
    if (type(observed_fee_lamports)is not int or observed_fee_lamports<0):
        report["reason"]="OBSERVED_TRANSACTION_FEE_LAMPORTS_MISSING"
        return report
    report["observed_fee_lamports"]=observed_fee_lamports
    # Fee amount must come from a separate observed fee receipt. CU is *not*
    # a fee, and simulated atomic logs alone do not prove fee assessment.
    if (type(start_mint_base_units_per_sol)is not int or
            start_mint_base_units_per_sol<=0 or conversion_authenticated is not True):
        report["reason"]="START_MINT_SOL_CONVERSION_NOT_AUTHENTICATED"
        return report
    if (not isinstance(downside_bps,(list,tuple)) or
            any(type(n)is not int or not 0<=n<=10_000 for n in downside_bps)):
        raise ValueError("invalid downside scenarios")
    fee=(observed_fee_lamports*start_mint_base_units_per_sol+
         LAMPORTS_PER_SOL-1)//LAMPORTS_PER_SOL
    report["fee_start_mint_base_units"]=fee
    report["fee_source_verified"]=True
    report["conversion_authenticated"]=True
    report["net_delta_start_mint_base_units"]=output-spent[0]-fee
    report["downside_scenarios"]=[{"output_haircut_bps":n,
        "net_delta_start_mint_base_units":output*(10_000-n)//10_000-spent[0]-fee}
        for n in downside_bps]
    report["status"]="COST_OBSERVATIONS_ACCOUNTED_SIMULATION_ONLY"
    # Fee claims and pricing input provenance are not independent economic
    # verification even when manually supplied; never approve a trade.
    return report
