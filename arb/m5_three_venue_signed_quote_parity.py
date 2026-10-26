"""Evidence-first diagnostic of each signed leg in a real three-venue triangle.

No RPC, no transaction submission and no implied independently verified quote.
"""
import json
import sys
from pathlib import Path
from arb.m5_three_distinct_venue_signed_acceptance import verify as accept
from arb.fixture_config_quote_projection import quote_cpmm_only
from arb.raydium_amm_v4_fixture_quote import quote_from_fixture
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def compare(fixture,receipt,*,observed_unix):
    result={"status":"BLOCKED","route_venues":fixture.get("route_venues"),
            "signed_execution_accepted":False,
            "independently_validated_quote_samples":0,"leg_comparisons":[],**SAFE}
    try:
        accept(fixture,receipt)
    except (ValueError,KeyError,TypeError) as exc:
        result["reason"]="SIGNED_THREE_VENUE_RECEIPT_NOT_ACCEPTED: "+str(exc)[:160]
        return result
    result["signed_execution_accepted"]=True
    amounts=receipt["planned_inputs"]
    hops=receipt.get("cpi_hops")
    before=receipt.get("initial_balances_base_units")
    after=receipt.get("positive_post_balances_base_units")
    if (not isinstance(hops,list) or len(hops)!=2
            or not isinstance(before,list) or not isinstance(after,list)
            or len(before)!=4 or len(after)!=4):
        result["reason"]="SIGNED_CPI_HOPS_NOT_AVAILABLE"
        return result
    if (any(type(x) is not int or x<0 for x in before+after)
            or any(type(x) is not int or x<=0 for x in amounts)
            or before[0]-after[0]!=amounts[0]
            or any(before[i]!=0 or after[i]!=0 for i in (1,2))):
        result["reason"]="SIGNED_SPL_ACCOUNT_RECONCILIATION_INVALID"
        return result
    if any(not isinstance(hops[i],dict) or hops[i].get("hop")!=i+1
           or hops[i].get("received_base_units")!=amounts[i+1]
           or hops[i].get("consumed_base_units")!=amounts[i+1]
           for i in (0,1)):
        result["reason"]="SIGNED_CPI_AMOUNT_CONSUMPTION_INVALID"
        return result
    mints=fixture["route_mints"]
    venues=fixture["route_venues"]
    pools=fixture["route_pool_addresses"]
    for i in range(3):
        row={"leg_index":i,"venue":venues[i],"pool":pools[i],
             "signed_input_base_units":amounts[i],
             "signed_output_base_units":None,"quoted_output_base_units":None,
             "deviation_bps":None,"quote_verified":False,**SAFE}
        # The coordinator's CPI audit emits per-hop receipt evidence;
        # never infer outputs from an indicative sequential quote chain.
        received=(hops[i].get("received_base_units") if isinstance(hops[i],dict)
                  and hops[i].get("hop")==i+1 else None) if i<2 else (
                  after[3]-before[3] if all(type(x)is int for x in before+after) else None)
        if type(received) is not int or received<=0:
            row["reason"]="SIGNED_HOP_OUTPUT_FIELD_NOT_INDEPENDENTLY_RESOLVED"
            result["leg_comparisons"].append(row)
            continue
        row["signed_output_base_units"]=received
        try:
            if venues[i]=="raydium_cpmm":
                leg={"venue":venues[i],"pool":pools[i],"input_mint":mints[i],
                     "output_mint":mints[i+1]}
                cpmm_result=quote_cpmm_only(fixture,observed_unix=observed_unix,
                                  leg=leg,amount_in=amounts[i])
                q=cpmm_result["quote"]
                interval=cpmm_result.get("native_fee_rounding_reference",{}).get(
                    "output_interval_base_units")
                if (isinstance(interval,list) and len(interval)==2
                        and all(type(v) is int and v>=0 for v in interval)
                        and interval[0]<=interval[1]):
                    row["cpmm_source_fee_rounding_output_interval_base_units"]=interval
                    row["signed_output_inside_cpmm_fee_rounding_interval"]=(
                        interval[0]<=received<=interval[1])
            elif venues[i]=="raydium_amm_v4":
                native_result=quote_from_fixture(fixture,pool=pools[i],input_mint=mints[i],
                    amount_in=amounts[i],observed_unix=observed_unix)
                q=native_result["quote"]
                fee_state=native_result.get("native_fee_fraction_reference")
                if isinstance(fee_state,dict):
                    row["native_fee_numerator"]=fee_state.get("fee_numerator")
                    row["native_fee_denominator"]=fee_state.get("fee_denominator")
                    row["native_fee_floor_input_units"]=fee_state.get("fee_floor_input_units")
                    row["native_fee_ceiling_input_units"]=fee_state.get("fee_ceiling_input_units")
                    row["native_adjusted_reserve_model"]=q.get("quote_model")
                    interval=fee_state.get("fee_rounding_output_interval_base_units")
                    if (isinstance(interval,list) and len(interval)==2
                            and all(type(v)is int and v>=0 for v in interval)
                            and interval[0]<=interval[1]):
                        row["native_fee_rounding_output_interval_base_units"]=interval
                        row["observed_output_within_fee_rounding_interval"]=(
                            interval[0]<=received<=interval[1])
                    row["native_fee_fraction_authenticated_quote"]=True
                    fee_min=fee_state.get("fee_floor_input_units")
                    fee_max=fee_state.get("fee_ceiling_input_units")
                    if (type(fee_min) is int and type(fee_max) is int
                            and 0<=fee_min<=fee_max<=amounts[i]):
                        row["native_fee_input_units_interval"]=[fee_min,fee_max]
                        row["native_fee_rounding_uncertainty_input_units"]=fee_max-fee_min
            else:
                raise ValueError("protocol directional fee/liquidity quote not independently implemented")
            if (q.get("venue")!=venues[i] or q.get("pool")!=pools[i]
                    or q.get("input_mint")!=mints[i] or
                    q.get("output_mint")!=mints[i+1] or
                    q.get("amount_in")!=amounts[i] or
                    q.get("snapshot_slot")!=fixture["state_accounts_observed_slot"]
                    or type(q.get("amount_out")) is not int or q["amount_out"]<=0):
                raise ValueError("account-derived quote source or direction mismatch")
            row["quoted_output_base_units"]=q["amount_out"]
            delta=q["amount_out"]-received
            row["signed_minus_quote_base_units"]=-delta
            row["signed_quote_exact_integer_match"]=(delta==0)
            row["absolute_error_base_units"]=abs(delta)
            # Integer bps truncation can be zero for real 1-unit errors.
            row["deviation_bps"]=abs(delta)*10000//received
            row["deviation_bps_ceiling"]=(abs(delta)*10000+received-1)//received
            row["reason"]="INDICATIVE_ONLY_SOURCE_EXECUTION_PROVENANCE_NOT_INDEPENDENTLY_VERIFIED"
        except (ValueError,TypeError,KeyError,ImportError,ArithmeticError) as exc:
            row["reason"]="SOURCE_EXACT_QUOTE_BLOCKED: "+str(exc)[:160]
        result["leg_comparisons"].append(row)
    result["signed_route_gross_delta_base_units"]=after[3]-before[3]-amounts[0]
    result["signed_route_output_base_units"]=after[3]-before[3]
    result["quoted_leg_count"]=sum(r["quoted_output_base_units"] is not None for r in result["leg_comparisons"])
    result["blocked_leg_count"]=len(result["leg_comparisons"])-result["quoted_leg_count"]
    result["minimum_observed_deviation_bps"]=min(
        (r["deviation_bps"] for r in result["leg_comparisons"] if r["deviation_bps"] is not None),
        default=None)
    result["maximum_observed_deviation_bps"]=max(
        (r["deviation_bps"] for r in result["leg_comparisons"] if r["deviation_bps"] is not None),
        default=None)
    result["exact_integer_indicative_matches"]=sum(
        r.get("signed_quote_exact_integer_match") is True for r in result["leg_comparisons"])
    result["native_fraction_fee_rounding_uncertainty_input_units"]=sum(
        r.get("native_fee_rounding_uncertainty_input_units",0)
        for r in result["leg_comparisons"])
    result["cpmm_source_fee_rounding_signed_legs_compared"]=sum(
        r.get("signed_output_inside_cpmm_fee_rounding_interval") is not None
        for r in result["leg_comparisons"])
    result["native_fraction_signed_legs_compared"]=sum(
        r.get("native_fee_fraction_authenticated_quote") is True
        and r.get("signed_minus_quote_base_units") is not None
        for r in result["leg_comparisons"])
    result["nonzero_errors_hidden_by_truncated_bps"]=sum(
        r.get("deviation_bps")==0 and r.get("absolute_error_base_units",0)>0
        for r in result["leg_comparisons"])
    result["status"]="SIGNED_EXECUTION_WITH_PER_LEG_PARITY_DIAGNOSTICS"
    return result

def main():
    if len(sys.argv)!=5:
        raise SystemExit("usage: source.json receipt.json observed_unix output.json")
    fixture=json.loads(Path(sys.argv[1]).read_text())
    receipt=json.loads(Path(sys.argv[2]).read_text())
    report=compare(fixture,receipt,observed_unix=int(sys.argv[3]))
    Path(sys.argv[4]).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":report["status"],
       "compared":sum(x["deviation_bps"] is not None for x in report["leg_comparisons"]),
       "independently_validated_quote_samples":0,"broadcast":False}))
if __name__=="__main__":main()
