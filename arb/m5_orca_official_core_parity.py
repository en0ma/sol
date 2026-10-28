"""Three-way Orca price acceptance: official Core, local integer model, signed SPL.

Only independently authenticated, signed isolated Surfpool receipts are used.
The official quote is calculated with unmodified orca_whirlpools_core 2.1.1.
Malformed source account bytes and missing execution Clock are hard failures.
"""
import argparse
import base64
import json
import subprocess
from pathlib import Path

from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_all_venue_signed_quotes import quote_leg
from arb.m5_four_to_six_source_signed_acceptance import assess
from arb.orca_adaptive_fee_source import source_oracle
from arb.orca_whirlpool import PROGRAM as WHIRLPOOL_PROGRAM, b58
from arb.whirlpool_ticks import (
    FIXED_LEN,DISC,DYNAMIC_DISC,DYNAMIC_MIN_LEN,DYNAMIC_MAX_LEN,
    decode_fixed_ticks,decode_dynamic_ticks,addresses)
from arb.source_snapshot_manifest import verify
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def source_core_inputs(fixture,index,*,specified_token_a=None):
    """Reconstruct exactly the official native quote inputs from the manifest."""
    verify(fixture)
    rows=extract_pool_states(fixture)
    if index!=len(rows)-1 or rows[index]["venue"]!="orca":
        raise ValueError("Orca must be terminal signed leg for SPL output proof")
    row=rows[index]
    pool=row["address"]
    state=row["decoded_pool_state"]
    if row["snapshot_slot"]!=fixture["state_accounts_observed_slot"]:
        raise ValueError("source Whirlpool slot mismatch")
    oracle=source_oracle(fixture,pool,state)
    if not isinstance(fixture.get("accounts"),dict):
        raise ValueError("authenticated fixture accounts missing")
    spacing=state["tick_spacing"]
    if type(spacing)is not int or spacing<=0:
        raise ValueError("invalid source tick spacing")
    arrays={}
    for address in fixture["state_account_addresses"]:
        account=fixture["accounts"].get(address)
        if not isinstance(account,dict) or account.get("owner")!=WHIRLPOOL_PROGRAM:
            continue
        if account.get("executable") is not False:
            raise ValueError("untrusted executable source tick")
        data=account.get("data")
        if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
            raise ValueError("source tick bytes malformed")
        raw=base64.b64decode(data[0],validate=True)
        fixed=len(raw)==FIXED_LEN and raw[:8]==DISC
        dynamic=(DYNAMIC_MIN_LEN<=len(raw)<=DYNAMIC_MAX_LEN and raw[:8]==DYNAMIC_DISC)
        if not (fixed or dynamic):
            continue
        parent=b58(raw[-32:]) if fixed else b58(raw[12:44])
        if parent!=pool:
            continue
        start=int.from_bytes(raw[8:12],"little",signed=True)
        if start in arrays or addresses(pool,[start])[0]!=address:
            raise ValueError("duplicate or forged source Whirlpool tick-array PDA")
        ticks=(decode_fixed_ticks(raw,pool,start,spacing) if fixed else
               decode_dynamic_ticks(raw,pool,start,spacing))
        arrays[start]={"start_tick":start,"ticks":ticks}
    if not arrays:
        raise ValueError("no source authenticated Orca tick array")
    direction=(fixture["route_mints"][index]==state["token_mint_a"] if specified_token_a is None
               else specified_token_a)
    if type(direction) is not bool:
        raise ValueError("Orca directional source selection must be boolean")
    if fixture["route_mints"][index] not in (state["token_mint_a"],state["token_mint_b"]):
        raise ValueError("source input mint missing from Whirlpool")
    from arb.whirlpool_ticks import start_tick
    span=88*spacing
    current=start_tick(state["tick_current_index"],spacing)
    ordered=[]
    while current in arrays and len(ordered)<6:
        ordered.append(arrays[current])
        current+=-span if direction else span
    if not ordered:
        raise ValueError("current source tick array unavailable")
    return {"pool":state,"oracle":oracle,"arrays":ordered,
            "specified_token_a":direction}

def compare_three_way(fixture,receipts,*,binary):
    rows=extract_pool_states(fixture)
    if any(fixture.get(k)is not False for k in SAFE):
        raise ValueError("source fixture must be offline")
    indexes=[i for i,r in enumerate(rows) if r["venue"]=="orca"]
    if len(indexes)!=1:
        raise ValueError("single Orca terminal signed leg required")
    index=indexes[0]
    base=source_core_inputs(fixture,index)
    if (not isinstance(receipts,dict) or len(receipts)<3 or
            any(type(k) is not int or not 0<k<2**64 for k in receipts)):
        raise ValueError("at least three distinct positive independently signed input sizes required")
    evidence=[]
    for size,receipt in sorted(receipts.items()):
        checked=assess(fixture,receipt)
        if checked["status"]!="VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK":
            raise ValueError("signed account/rollback provenance not verified")
        amounts=receipt.get("planned_inputs")
        after=receipt.get("positive_post_balances_base_units")
        if (not isinstance(amounts,list) or len(amounts)!=len(rows) or
                amounts[0]!=size or not isinstance(after,list) or
                len(after)!=len(rows)+1 or type(after[-1]) is not int):
            raise ValueError("genuine signed SPL input/output evidence missing")
        clock=receipt.get("orca_fork_clock_evidence")
        if (not isinstance(clock,dict) or
                clock.get("status")!="ORCA_FORK_CLOCK_STABLE_FOR_SIGNED_ATTEMPT" or
                clock.get("fork_clock_stable_for_quote") is not True or
                any(clock.get(k)is not False for k in SAFE) or
                type(clock.get("fork_unix_timestamp"))is not int or
                clock["fork_unix_timestamp"]<=0):
            raise ValueError("signed Orca execution Clock evidence missing")
        before=clock.get("fork_clock_before")
        after_clock=clock.get("fork_clock_after")
        if (not isinstance(before,dict) or not isinstance(after_clock,dict) or
                before.get("clock_source")!="ISOLATED_SURFPOOL_CLOCK_SYSVAR" or
                after_clock.get("clock_source")!="ISOLATED_SURFPOOL_CLOCK_SYSVAR" or
                any(before.get(k)is not False or after_clock.get(k)is not False
                    for k in SAFE) or
                before.get("fork_clock_slot")!=after_clock.get("fork_clock_slot") or
                before.get("fork_unix_timestamp")!=clock["fork_unix_timestamp"] or
                after_clock.get("fork_unix_timestamp")!=clock["fork_unix_timestamp"]):
            raise ValueError("signed fork clock slot/timestamp was not fixed for quote")
        timestamp=clock["fork_unix_timestamp"]
        request={**base,"amount_in":amounts[index],
                 "fork_unix_timestamp":timestamp}
        result=subprocess.run([binary],input=json.dumps(request),text=True,
                              capture_output=True,timeout=30,check=False)
        if result.returncode!=0:
            raise ValueError("official Orca Core quote refused source state: "+
                             result.stderr[:500])
        official=json.loads(result.stdout)
        native=quote_leg(fixture,leg_index=index,
                         amount_in=amounts[index],observed_unix=timestamp)
        local=native.get("predicted_output_base_units")
        actual=after[-1]
        official_amount=official.get("amount_out")
        if (type(official_amount)is not int or type(local)is not int or
                native.get("quote_status")!="SOURCE_BOUND_INDICATIVE"):
            raise ValueError("source-native models did not calculate integer output")
        evidence.append({"initial_size_base_units":size,
                         "orca_exact_input_base_units":amounts[index],
                         "signed_spl_output_base_units":actual,
                         "official_orca_core_output_base_units":official_amount,
                         "local_python_output_base_units":local,
                         "official_minus_signed":official_amount-actual,
                         "python_minus_signed":local-actual,
                         "fork_execution_unix_timestamp":timestamp,
                         "source_slot":fixture["state_accounts_observed_slot"],
                         **SAFE})
    if len({r["orca_exact_input_base_units"] for r in evidence})!=len(evidence):
        raise ValueError("repeated Orca exact input cannot establish multi-size parity")
    if len({r["source_slot"] for r in evidence})!=1:
        raise ValueError("mixed source slots cannot establish native parity")
    matches=sum(r["official_minus_signed"]==r["python_minus_signed"]==0
                for r in evidence)
    return {"status":("ORCA_THREE_WAY_SIGNED_NATIVE_PARITY_VERIFIED"
                      if matches==len(evidence)
                      else "ORCA_THREE_WAY_NATIVE_PARITY_MISMATCH"),
            "exact_three_way_match_count":matches,"sample_count":len(evidence),
            "all_samples_match":matches==len(evidence),
            "official_library":"orca_whirlpools_core",
            "official_library_version":"2.1.1","samples":evidence,
            "protocol_exact_all_pools_verified":False,**SAFE}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--fixture",required=True)
    p.add_argument("--receipts",required=True)
    p.add_argument("--binary",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--amounts",default="10000,100000,1000000")
    a=p.parse_args()
    sizes=tuple(int(x) for x in a.amounts.split(","))
    receipts={x:json.loads((Path(a.receipts)/("signed-size-"+str(x)+".json")).read_text())
              for x in sizes}
    report=compare_three_way(json.loads(Path(a.fixture).read_text()),receipts,
                             binary=a.binary)
    Path(a.output).write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
                      "exact_three_way_match_count":report["exact_three_way_match_count"],
                      "sample_count":report["sample_count"],**SAFE}))
    if not report["all_samples_match"]:
        raise SystemExit("official Orca Core/local native/signed fork SPL mismatch")

if __name__=="__main__":
    main()
