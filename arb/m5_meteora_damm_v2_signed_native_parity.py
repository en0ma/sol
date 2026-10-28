"""Meteora DAMM v2 first executable pricing reconciliation against signed Surfpool.

Read signed per-leg SPL transfers, authenticated Pool fee schedule and reserves.
A dynamic fee or curve discrepancy is reported, never replaced by a guessed fee.
"""
import argparse,json,base64,subprocess
from pathlib import Path
from arb.source_snapshot_manifest import verify
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.m5_four_to_six_source_signed_acceptance import assess
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def compare(fixture,receipt,*,binary):
    verify(fixture)
    if any(fixture.get(k)is not False or receipt.get(k)is not False for k in SAFE):
        raise ValueError("safe authenticated fixture and signed receipt required")
    verdict=assess(fixture,receipt)
    if verdict.get("status")!="VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK":
        raise ValueError("independent signature/CPI/rollback audit failed")
    rows=extract_pool_states(fixture)
    targets=[i for i,row in enumerate(rows) if row["venue"]=="meteora_damm_v2"]
    if len(targets)!=1:
        raise ValueError("exactly one DAMM v2 source pool required")
    i=targets[0]
    prefix=receipt.get("signed_prefix_observations")
    planned=receipt.get("planned_inputs")
    if (not isinstance(planned,list) or len(planned)!=len(rows) or
            not isinstance(prefix,list) or len(prefix)!=len(rows)-1 or
            i>=len(prefix) or prefix[i].get("index")!=i or
            prefix[i].get("venue")!="meteora_damm_v2" or
            prefix[i].get("pool")!=rows[i]["address"] or
            prefix[i].get("amount_in")!=planned[i] or
            prefix[i].get("observed_output")!=planned[i+1]):
        raise ValueError("authenticated DAMM signed prefix is absent")
    clock=receipt.get("orca_fork_clock_evidence")
    if (not isinstance(clock,dict) or
            clock.get("status")!="ORCA_FORK_CLOCK_STABLE_FOR_SIGNED_ATTEMPT" or
            clock.get("fork_clock_stable_for_quote") is not True or
            type(clock.get("fork_unix_timestamp"))is not int):
        raise ValueError("real signed fork execution Clock required")
    row=rows[i]
    state=row["decoded_pool_state"]
    pool=row["address"]
    before=clock.get("fork_clock_before")
    after=clock.get("fork_clock_after")
    if (not isinstance(before,dict) or not isinstance(after,dict) or
            before.get("fork_clock_slot")!=after.get("fork_clock_slot") or
            before.get("fork_unix_timestamp")!=after.get("fork_unix_timestamp") or
            before.get("fork_unix_timestamp")!=clock["fork_unix_timestamp"]):
        raise ValueError("DAMM signed Clock slot and time not pinned")
    pool_account=fixture["accounts"].get(pool)
    if not isinstance(pool_account,dict):
        raise ValueError("source Meteora pool bytes missing")
    from arb.meteora_damm_v2_native_quote import quote_pool_account
    result=quote_pool_account(pool_account,
        mint_in=fixture["route_mints"][i],
        amount_in=planned[i],
        fork_unix_timestamp=clock["fork_unix_timestamp"],
        fork_clock_slot=before["fork_clock_slot"],binary=binary)
    official_output=result["amount_out"]
    signed=planned[i+1]
    parity=official_output==signed
    return {"status":("DAMM_V2_OFFICIAL_SDK_SIGNED_EXACT_MATCH" if parity
                      else "DAMM_V2_OFFICIAL_SDK_SIGNED_MISMATCH"),
            "source_slot":fixture["state_accounts_observed_slot"],
            "pool":pool,"amount_in_base_units":planned[i],
            "signed_output_base_units":signed,
            "official_meteora_sdk_output_base_units":official_output,
            "official_minus_signed":official_output-signed,
            "official_signed_parity_verified":parity,
            "native_pricing_engine":"OFFICIAL_METEORA_RUST_SDK",
            "fork_execution_unix_timestamp":clock["fork_unix_timestamp"],
            "signed_execution_authenticated":True,
            "protocol_exact_verified":parity,**SAFE}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--fixture",required=True)
    p.add_argument("--receipts",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--binary",required=True)
    p.add_argument("--amounts",default="10000,100000,1000000")
    a=p.parse_args()
    fixture=json.loads(Path(a.fixture).read_text())
    trials=[]
    for amount in (int(x) for x in a.amounts.split(",")):
        receipt=json.loads((Path(a.receipts)/("signed-size-"+str(amount)+".json")).read_text())
        try:
            evidence=compare(fixture,receipt,binary=a.binary)
        except (ValueError,TypeError,KeyError,OverflowError) as exc:
            evidence={"status":"DAMM_V2_SOURCE_SIGNED_RECONCILIATION_BLOCKED",
                      "reason":str(exc)[:300],"protocol_exact_verified":False,**SAFE}
        evidence["initial_route_input_base_units"]=amount
        trials.append(evidence)
    matched=sum(x.get("protocol_exact_verified") is True for x in trials)
    official_matched=sum(x.get("official_signed_parity_verified") is True for x in trials)
    result={"status":("DAMM_V2_SIGNED_NATIVE_PRICING_VALIDATED" if matched==len(trials)
                      else "DAMM_V2_SIGNED_NATIVE_PRICING_UNVERIFIED"),
            "matched":matched,"official_signed_matches":official_matched,
            "sample_count":len(trials),"trials":trials,
            "protocol_exact_verified":matched==len(trials),**SAFE}
    Path(a.output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":result["status"],"matched":matched,
                      "official_signed_matches":official_matched,
                      "sample_count":len(trials),**SAFE}))
    # A blocked actual fee regime is never promoted to pricing acceptance.
    # This diagnostic runner does not block other-venue CI independently.
if __name__=="__main__":
    main()
