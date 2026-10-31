"""Independent Orca Core versus local integer quote: both directions and real tick events.

This matrix is protocol-reference validation, NOT signed Surfpool acceptance.
A scenario is successful only when official library and local native output
agree at the exact same source inputs, including an initialized liquidity tick.
"""
import argparse
import json
import subprocess
from arb.orca_adaptive_fee_source import quote_adaptive_from_arrays
from arb.orca_tick_math import sqrt_price_from_tick_index
from arb.whirlpool_ticks import start_tick

SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
CLOCK=1793159406
A="So11111111111111111111111111111111111111112"
B="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"

def oracle(*,clock=CLOCK,fee_age=40):
    return {"trade_enable_timestamp":0,"oracle_layout_authenticated":True,
        "constants":{"filter_period":30,"decay_period":600,
            "reduction_factor":5000,"adaptive_fee_control_factor":60000,
            "max_volatility_accumulator":880000,"tick_group_size":4,
            "major_swap_threshold_ticks":4},
        "variables":{"last_reference_update_timestamp":clock-fee_age,
            "last_major_swap_timestamp":clock-fee_age,
            "volatility_reference":14000,
            "tick_group_index_reference":0,
            "volatility_accumulator":24000},
        **SAFE}

def scenario(direction,amount,cross,*,fee_age=40):
    if direction not in ("a_to_b","b_to_a"):
        raise ValueError("invalid test direction")
    if type(amount)is not int or amount<=0:
        raise ValueError("invalid reference input")
    state={"fee_tier_index_seed":8,"tick_spacing":4,
        "fee_rate_hundredths_bps":400,"protocol_fee_rate":300,
        "token_mint_a":A,"token_mint_b":B,
        "liquidity":"10000000000",
        "sqrt_price_x64":str(sqrt_price_from_tick_index(0)),
        "tick_current_index":0}
    down=direction=="a_to_b"
    starts=([start_tick(0,4),start_tick(0,4)-352] if down
            else [start_tick(0,4),start_tick(0,4)+352])
    tick=-4 if down else 4
    liquidity=1_000_000_000 if down else -1_000_000_000
    arrays=[]
    for st in starts:
        rows=[]
        if cross and st<=tick<st+352:
            rows=[{"tick_index":tick,"liquidity_net":str(liquidity),
                   "liquidity_gross":str(abs(liquidity))}]
        arrays.append({"status":"FIXED_VALID","start_tick":st,"ticks":rows})
    return state,arrays,oracle(fee_age=fee_age)

def run(binary):
    scenarios=[
        ("a_to_b",100_000,False),("b_to_a",100_000,False),
        ("a_to_b",1_000_000,False),("b_to_a",1_000_000,False),
        ("a_to_b",20_000_000,True),("b_to_a",20_000_000,True),
        ("a_to_b",50_000_000,True),("b_to_a",50_000_000,True),
    ]
    rows=[]
    for fee_age in (0,40,300,700,4000):
      for direction,amount,cross in scenarios:
        state,arrays,fee= scenario(direction,amount,cross,fee_age=fee_age)
        request={"pool":state,"oracle":fee,"arrays":arrays,
                 "amount_in":amount,"specified_token_a":direction=="a_to_b",
                 "fork_unix_timestamp":CLOCK}
        result=subprocess.run([binary],input=json.dumps(request),text=True,
            capture_output=True,timeout=30,check=False)
        if result.returncode:
            rows.append({"direction":direction,"amount_in":amount,
                         "cross":cross,"fee_reference_age_seconds":fee_age,"status":"OFFICIAL_ORCA_CORE_REJECTED",
                         "reason":result.stderr[-500:],**SAFE})
            continue
        reference=json.loads(result.stdout)["amount_out"]
        try:
            model=quote_adaptive_from_arrays(
                state,A if direction=="a_to_b" else B,amount,
                arrays,fee,observed_unix=CLOCK)
            native=model["estimated_output_base_units"]
            crossed=model["crossed_initialized_ticks"]
            actual_cross=bool(crossed)
            correct=(reference==native and (not cross or actual_cross))
            rows.append({"direction":direction,"amount_in":amount,
                         "cross_requested":cross,"fee_reference_age_seconds":fee_age,
                         "cross_observed":actual_cross,
                         "initialized_ticks_crossed":crossed,
                         "official_orca_core_output_base_units":reference,
                         "local_python_output_base_units":native,
                         "difference":native-reference,
                         "status":("OFFICIAL_NATIVE_PARITY" if correct
                                   else "OFFICIAL_NATIVE_MISMATCH"),**SAFE})
        except (ValueError,TypeError,KeyError) as exc:
            rows.append({"direction":direction,"amount_in":amount,
                         "cross_requested":cross,
                         "status":"LOCAL_NATIVE_QUOTE_REJECTED",
                         "reason":str(exc),**SAFE})
    accepted=sum(x["status"]=="OFFICIAL_NATIVE_PARITY" for x in rows)
    return {"status":("ORCA_OFFICIAL_REFERENCE_BIDIRECTIONAL_ALL_MATCH"
                      if accepted==len(rows)
                      else "ORCA_OFFICIAL_REFERENCE_BIDIRECTIONAL_MISMATCH"),
            "tested":len(rows),"exact_matches":accepted,
            "tests":rows,"signed_fork_acceptance":False,
            "source":"DETERMINISTIC_SYNTHETIC_REFERENCE_VECTOR",
            **SAFE}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--binary",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=run(a.binary)
    from pathlib import Path
    Path(a.output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":result["status"],
                       "tested":result["tested"],
                       "exact_matches":result["exact_matches"],**SAFE}))
    if result["tested"]!=result["exact_matches"]:
        for case in result["tests"]:
            if case["status"]!="OFFICIAL_NATIVE_PARITY":
                print(json.dumps(case))
        raise SystemExit(1)

if __name__=="__main__":
    main()
