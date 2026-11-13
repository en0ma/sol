"""Independently accept real signed DAMM-v2 -> CPMM fork artifacts only.

Consume actual saved Surfpool execution output, not builder inventories,
fixture exports, mocks or CI exit codes. Pair credit is directional.
"""
import argparse
import json
from pathlib import Path
from arb.damm_cpmm_atomic_offline import DAMM, CPMM, DAMM_POOL, CPMM_POOL, SAFETY

STATUS="SIGNED_ATOMIC_TWO_VENUE_AND_ROLLBACK_VERIFIED"
FIRST="meteora_damm_v2"
SECOND="raydium_cpmm"

def accept(evidence):
    errors=[]
    if not isinstance(evidence,dict):
        evidence={}
        errors.append("missing execution evidence")
    for key,value in SAFETY.items():
        if evidence.get(key) is not value:
            errors.append("unsafe or absent "+key)
    if evidence.get("status")!=STATUS:
        errors.append("signed atomic status unverified")
    for key in ("signed_atomic_simulation_verified","rollback_failure_case_verified",
                "intermediate_intra_transaction_consumption_verified",
                "instruction_order_verified","failed_at_second_instruction_after_successful_first"):
        if evidence.get(key) is not True:
            errors.append("missing verified "+key)
    if evidence.get("damm_pool")!=DAMM_POOL or evidence.get("cpmm_pool")!=CPMM_POOL:
        errors.append("authenticated pool pair mismatch")
    if evidence.get("top_level_venue_events")!=[
        [DAMM,"invoke"],[DAMM,"success"],[CPMM,"invoke"],[CPMM,"success"]]:
        errors.append("positive instruction sequence mismatch")
    if evidence.get("negative_top_level_venue_events")!=[
        [DAMM,"invoke"],[DAMM,"success"],[CPMM,"invoke"],[CPMM,"failed"]]:
        errors.append("negative instruction sequence mismatch")
    if "InstructionError': [1, {'Custom': 6005}]" not in evidence.get("negative_error",""):
        errors.append("CPMM instruction-1 slippage error missing")
    if not any("ExceededSlippage" in line and "6005" in line
               for line in (evidence.get("negative_logs") or []) if isinstance(line,str)):
        errors.append("CPMM slippage runtime log missing")
    start=evidence.get("initial_balances_base_units")
    after=evidence.get("positive_post_balances_base_units")
    persistent=evidence.get("negative_persistent_balances_base_units")
    transferred=evidence.get("first_leg_intermediate_received_base_units")
    consumed=evidence.get("second_leg_intermediate_consumed_base_units")
    if (not all(isinstance(x,list) and len(x)==3 and
                all(type(v) is int and v>=0 for v in x)
                for x in (start,after,persistent))):
        errors.append("invalid account balance snapshots")
    else:
        if start[1:]!=[0,0] or start[0]<=0:
            errors.append("invalid starting liquidity")
        if persistent!=start:
            errors.append("negative persisted balances mismatch")
        if after[0]!=start[0]-evidence.get("terminal_input_spent_base_units",-1):
            errors.append("input balance reconciliation mismatch")
        if after[2]!=evidence.get("terminal_output_received_base_units"):
            errors.append("output balance reconciliation mismatch")
        if type(transferred) is not int or type(consumed) is not int or not 0<consumed<=transferred:
            errors.append("invalid intermediate CPI amounts")
        elif after[1]!=start[1]+transferred-consumed:
            errors.append("intermediate not reconciled")
    signature=evidence.get("signature")
    packet=evidence.get("signed_packet_bytes")
    if not isinstance(signature,str) or not 80<=len(signature)<=90:
        errors.append("missing signed transaction identity")
    if type(packet) is not int or not 100<=packet<=1232:
        errors.append("missing Solana signed packet size")
    if evidence.get("positive_error")!="None":
        errors.append("positive simulation error is nonempty")
    if (not isinstance(evidence.get("positive_logs"),list)
            or not evidence["positive_logs"]):
        errors.append("missing positive execution trace")
    if (type(evidence.get("first_leg_output_floor")) is not int
            or evidence["first_leg_output_floor"]<=0
            or evidence.get("second_leg_input_base_units")!=consumed):
        errors.append("requested intermediate input not evidenced")
    if not isinstance(evidence.get("mints"),list) or len(evidence["mints"])!=3:
        errors.append("mint path metadata missing")
    elif (evidence["mints"][0]!=evidence["mints"][2]
          or evidence["mints"][0]==evidence["mints"][1]):
        errors.append("unexpected closed-loop mint continuity")
    if evidence.get("negative_simulation_post_accounts_available") is True:
        if evidence.get("negative_simulation_post_balances_base_units")!=start:
            errors.append("negative returned post-state did not roll back")
    elif evidence.get("rollback_evidence_mode")!="atomic_abort_instruction_1_and_persistence":
        errors.append("negative rollback evidence provenance missing")
    count=0 if errors else 1
    return {"status":"ACCEPTED_LOCAL_SIGNED_ATOMIC_PAIR" if count else "UNVERIFIED",
            "verified_ordered_pair_count":count,"ordered_pair_target":42,
            "verified_pair":{"first_venue":FIRST,"second_venue":SECOND,
                             "first_pool":DAMM_POOL,"second_pool":CPMM_POOL}
                            if count else None,
            "positive_signed_packet_bytes":evidence.get("signed_packet_bytes"),
            "rollback_evidence_mode":evidence.get("rollback_evidence_mode"),
            "failure_reasons":errors,**SAFETY}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    result=accept(json.loads(Path(args.input).read_text()))
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
    if result["verified_ordered_pair_count"]!=1:
        raise SystemExit(2)

if __name__=="__main__":
    main()
