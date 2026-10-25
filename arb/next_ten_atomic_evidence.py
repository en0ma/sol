"""Evidence-driven ten-route expansion report.

Read actual per-route isolated-Surfpool JSON artifacts. Never promote a builder,
unit test, fixture export, or one-leg success into pair coverage.
"""
import argparse
import json
from pathlib import Path
from arb.next_ten_atomic_routes import BATCH_10,route_batch
from arb.execution_target_matrix import TARGET_VENUES

SAFETY={"actionable":False,"live_execution_approved":False,"broadcast":False}
REQUIRED_TRUE=(
    "signed_atomic_simulation_verified",
    "intermediate_intra_transaction_consumption_verified",
    "rollback_failure_case_verified",
    "instruction_order_verified",
    "failed_at_second_instruction_after_successful_first",
)

def assess(route, evidence):
    first,second=route
    errors=[]
    if not isinstance(evidence,dict):
        evidence={}
    if (evidence.get("first_venue"),evidence.get("second_venue"))!=route:
        errors.append("directional venue identity missing or mismatched")
    for key,expected in SAFETY.items():
        if evidence.get(key) is not expected:
            errors.append("unsafe "+key)
    for key in REQUIRED_TRUE:
        if evidence.get(key) is not True:
            errors.append("missing actual "+key)
    if evidence.get("execution_environment")!="ISOLATED_SURFPOOL_OFFLINE":
        errors.append("isolated Surfpool runtime provenance missing")
    if evidence.get("signed_transaction_verified") is not True:
        errors.append("signed message cryptographic verification missing")
    if not isinstance(evidence.get("transaction_signature"),str) or not evidence["transaction_signature"]:
        errors.append("signed transaction identity missing")
    packet=evidence.get("signed_packet_bytes")
    if type(packet) is not int or not 100<=packet<=1232:
        errors.append("invalid packet length")
    invoked=evidence.get("positive_top_level_venues")
    negative=evidence.get("negative_top_level_venues")
    if invoked!=[first,second] or negative!=[first,second]:
        errors.append("ordered positive/negative venue programs not proven")
    mints=evidence.get("route_mints")
    if not isinstance(mints,list) or len(mints)!=3 or any(not isinstance(m,str) or not m for m in mints):
        errors.append("three authenticated route mints missing")
    elif mints[0]!=mints[2] or mints[0]==mints[1]:
        errors.append("closed cycle mint continuity invalid")
    # Quote-to-execution source binding is an additional, distinct M5 gate.
    # Legacy accepted 42/42 proof cannot acquire a slot claim by assertion.
    pool_addresses=evidence.get("route_pool_addresses")
    if pool_addresses is not None and (
        not isinstance(pool_addresses,list) or len(pool_addresses)!=2 or
        any(not isinstance(p,str) or not p for p in pool_addresses)):
        errors.append("invalid signed route pool provenance")
    if evidence.get("quote_accuracy_verified") is True:
        errors.append("quote accuracy incorrectly self-certified by atomic receipt")
    balances=evidence.get("initial_balances_base_units")
    post=evidence.get("positive_post_balances_base_units")
    persistent=evidence.get("negative_persistent_balances_base_units")
    if not all(isinstance(row,list) and len(row)==3 and
               all(type(v) is int and 0<=v<2**64 for v in row)
               for row in (balances,post,persistent)):
        errors.append("actual SPL balances absent")
    else:
        if balances[0]<=0 or balances[1:]!=[0,0] or persistent!=balances:
            errors.append("funding or rollback snapshot invalid")
        received=evidence.get("first_leg_intermediate_received_base_units")
        consumed=evidence.get("second_leg_intermediate_consumed_base_units")
        if type(received) is not int or type(consumed) is not int or not 0<consumed<=received:
            errors.append("intermediate SPL CPI deltas absent")
        elif post[1]!=received-consumed:
            errors.append("SPL intermediate delta reconciliation failed")
        if not (0<=post[0]<balances[0] and post[2]>0):
            errors.append("input/output balance movement invalid")
    if evidence.get("positive_error")!="None":
        errors.append("positive signed transaction returned an error")
    if evidence.get("status")!="SIGNED_ATOMIC_AND_ROLLBACK_VERIFIED":
        errors.append("signed atomic runtime status not verified")
    if not isinstance(evidence.get("negative_error"),str) or "InstructionError" not in evidence["negative_error"]:
        errors.append("negative instruction error not observed")
    if evidence.get("second_leg_failure_instruction_index")!=1:
        errors.append("negative case did not fail at instruction 1")
    if not isinstance(evidence.get("positive_logs"),list) or not evidence["positive_logs"]:
        errors.append("positive runtime logs absent")
    if not isinstance(evidence.get("negative_logs"),list) or not evidence["negative_logs"]:
        errors.append("negative runtime logs absent")
    return {"first_venue":first,"second_venue":second,
            "status":"VERIFIED" if not errors else "UNVERIFIED",
            "failure_reasons":errors,**SAFETY}

def build(evidence_by_route,*,batch=BATCH_10):
    keys=set(batch)
    if set(evidence_by_route)-keys:
        raise ValueError("unrecognized or non-batch route")
    rows=[assess(route,evidence_by_route.get(route)) for route in batch]
    count=sum(r["status"]=="VERIFIED" for r in rows)
    return {"status":"NEXT_TEN_REAL_FORK_EXECUTION_EVIDENCE",
            "batch_target":len(batch),"batch_verified":count,
            "batch_unverified":len(batch)-count,"routes":rows,**SAFETY}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--evidence-dir",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--batch",choices=("first","next","remaining"),default="first")
    args=p.parse_args()
    root=Path(args.evidence_dir)
    evidence={}
    for first,second in route_batch(args.batch):
        path=root/(first+"__"+second+".json")
        if path.is_file():
            evidence[(first,second)]=json.loads(path.read_text())
    report=build(evidence,batch=route_batch(args.batch))
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"batch_verified":report["batch_verified"],
                      "batch_target":report["batch_target"],"broadcast":False}))
if __name__=="__main__":
    main()
