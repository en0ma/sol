"""Independent adaptive amount-continuity acceptance from real signed receipts.

The legacy atomic 42-route acceptance does not imply adaptive continuity.
This gate is strictly isolated Surfpool simulation, not quote accuracy or
upstream source attestation. Every route must pass signed rollback proof.
"""
import argparse
import json
from pathlib import Path
from arb.next_ten_atomic_evidence import assess
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
PAIRS=(("raydium_cpmm","raydium_amm_v4"),("raydium_amm_v4","raydium_cpmm"))

def check(route,receipt):
    signed=assess(route,receipt)
    reasons=list(signed["failure_reasons"])
    if receipt.get("adaptive_second_input_verified_against_atomic_output") is not True:
        reasons.append("adaptive output not matched in signed atomic execution")
    if receipt.get("signed_second_leg_consumes_full_first_output") is not True:
        reasons.append("first output not fully consumed")
    plan=receipt.get("adaptive_cpmm_v4_amount_planning")
    if not isinstance(plan,dict) or plan.get("standalone_signed") is not True:
        reasons.append("signed first-leg amount preflight absent")
    else:
        n=plan.get("planned_second_input")
        if type(n)is not int or not 0<n<2**64 or n!=receipt.get("declared_second_leg_input_base_units"):
            reasons.append("preflight amount not bound to second signed instruction")
    received=receipt.get("first_leg_intermediate_received_base_units")
    consumed=receipt.get("second_leg_intermediate_consumed_base_units")
    if type(received)is not int or type(consumed)is not int or not 0<received==consumed:
        reasons.append("signed intermediate SPL CPI flow not fully consumed")
    if receipt.get("signed_intermediate_surplus_base_units")!=0:
        reasons.append("positive signed intermediate SPL surplus nonzero")
    return {"route":"__".join(route),"status":"VERIFIED_ADAPTIVE_SIGNED_OFFLINE" if not reasons else "UNVERIFIED",
            "failure_reasons":reasons,"source_rpc_independently_attested":False,
            "quote_accuracy_verified":False,**SAFE}

def audit(root):
    root=Path(root)
    rows=[]
    for route in PAIRS:
        p=root/("__".join(route)+".json")
        if not p.is_file():
            rows.append({"route":"__".join(route),"status":"UNVERIFIED",
                         "failure_reasons":["adaptive signed receipt missing"],**SAFE})
            continue
        try:
            receipt=json.loads(p.read_text())
            rows.append(check(route,receipt))
        except (ValueError,TypeError,KeyError,OSError) as exc:
            rows.append({"route":"__".join(route),"status":"UNVERIFIED",
                         "failure_reasons":["receipt unreadable: "+str(exc)[:160]],**SAFE})
    verified=sum(r["status"]=="VERIFIED_ADAPTIVE_SIGNED_OFFLINE" for r in rows)
    return {"status":"ADAPTIVE_SIGNED_OFFLINE_ACCEPTANCE","target":2,"verified":verified,
            "routes":rows,"independently_validated_quote_samples":0,
            "full_42_adaptive_verified":False,**SAFE}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--receipts",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    result=audit(a.receipts)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"verified":result["verified"],"target":2,**SAFE}))
    return 0 if result["verified"]==2 else 1
if __name__=="__main__":raise SystemExit(main())
