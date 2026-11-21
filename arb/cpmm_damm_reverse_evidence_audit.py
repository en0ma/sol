"""Independent fail-closed acceptance for reverse CPMM -> DAMM Surfpool evidence."""
import json
import argparse
from pathlib import Path
from arb.damm_cpmm_atomic_offline import DAMM, CPMM, DAMM_POOL, CPMM_POOL, SAFETY

def accept_reverse(e):
    errors=[]
    if not isinstance(e,dict):
        e={}
    for key,value in SAFETY.items():
        if e.get(key) is not value:
            errors.append("unsafe flag: "+key)
    required=("signed_atomic_simulation_verified","rollback_failure_case_verified",
              "intermediate_intra_transaction_consumption_verified",
              "instruction_order_verified","failed_at_second_instruction_after_successful_first")
    for key in required:
        if e.get(key) is not True:
            errors.append("not verified: "+key)
    if e.get("status")!="SIGNED_REVERSE_ATOMIC_AND_ROLLBACK_VERIFIED":
        errors.append("missing verified reverse execution status")
    if (e.get("first_venue"),e.get("second_venue"))!=("raydium_cpmm","meteora_damm_v2"):
        errors.append("wrong ordered pair")
    if (e.get("cpmm_pool"),e.get("damm_pool"))!=(CPMM_POOL,DAMM_POOL):
        errors.append("wrong authenticated pools")
    if e.get("top_level_venue_events")!=[
        [CPMM,"invoke"],[CPMM,"success"],[DAMM,"invoke"],[DAMM,"success"]]:
        errors.append("positive venue order invalid")
    if e.get("negative_top_level_venue_events")!=[
        [CPMM,"invoke"],[CPMM,"success"],[DAMM,"invoke"],[DAMM,"failed"]]:
        errors.append("negative venue order invalid")
    if e.get("negative_error")!="{'InstructionError': [1, {'Custom': 6002}]}":
        errors.append("expected DAMM instruction-1 slippage error absent")
    if not any("ExceededSlippage" in line for line in (e.get("negative_logs") or [])
               if isinstance(line,str)):
        errors.append("DAMM slippage trace missing")
    initial=e.get("initial_balances_base_units")
    positive=e.get("positive_post_balances_base_units")
    persistent=e.get("negative_persistent_balances_base_units")
    produced=e.get("first_leg_intermediate_received_base_units")
    consumed=e.get("second_leg_intermediate_consumed_base_units")
    if not all(isinstance(row,list) and len(row)==3 and
               all(type(n) is int and n>=0 for n in row)
               for row in (initial,positive,persistent)):
        errors.append("missing actual SPL balance snapshots")
    else:
        if not initial[0]>0 or initial[1:]!=[0,0] or persistent!=initial:
            errors.append("starting or persistent balance inconsistent")
        if not (type(produced) is int and type(consumed) is int and 0<consumed<=produced):
            errors.append("intermediate CPI amounts invalid")
        elif positive[1]!=produced-consumed:
            errors.append("intermediate token not reconciled")
        if (positive[0]!=initial[0]-e.get("terminal_input_spent_base_units",-1)
                or positive[2]!=e.get("terminal_output_received_base_units")):
            errors.append("terminal SPL balance mismatch")
    if (e.get("negative_simulation_post_accounts_available") is True
            and e.get("negative_simulation_post_balances_base_units")!=initial):
        errors.append("failed simulated accounts not rolled back")
    if e.get("rollback_evidence_mode") not in (
        "failed_post_state_and_persistence","atomic_abort_instruction_1_and_persistence"):
        errors.append("missing rollback evidence provenance")
    if e.get("positive_error")!="None":
        errors.append("positive swap simulation failed")
    if type(e.get("signed_packet_bytes")) is not int or not 100<=e["signed_packet_bytes"]<=1232:
        errors.append("signed packet absent")
    if not isinstance(e.get("signature"),str) or not 80<=len(e["signature"])<=90:
        errors.append("signed transaction signature absent")
    if e.get("second_leg_input_base_units")!=consumed:
        errors.append("second-leg input mismatch")
    ok=not errors
    return {"status":"ACCEPTED_LOCAL_SIGNED_REVERSE_ATOMIC_PAIR" if ok else "UNVERIFIED",
            "verified_ordered_pair_count":int(ok),
            "verified_pair":{"first_venue":"raydium_cpmm","second_venue":"meteora_damm_v2"}
                            if ok else None,
            "failure_reasons":errors,**SAFETY}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    result=accept_reverse(json.loads(Path(args.input).read_text()))
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
    if result["verified_ordered_pair_count"]!=1:
        raise SystemExit(2)
if __name__=="__main__":
    main()
