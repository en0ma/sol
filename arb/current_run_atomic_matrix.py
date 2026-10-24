"""Current-run ordered venue matrix populated ONLY by accepted real fork artifacts."""
import argparse
import json
from pathlib import Path
from arb.execution_target_matrix import execution_matrix
from arb.damm_cpmm_atomic_evidence_audit import accept, FIRST, SECOND

def reconcile(evidence):
    report=execution_matrix()
    proof=accept(evidence)
    accepted=proof["verified_ordered_pair_count"]==1
    for row in report["ordered_pairs"]:
        matching=(row["first_venue"],row["second_venue"])==(FIRST,SECOND)
        if accepted and matching:
            row.update(this_execution_order_verified=True,
                       current_run_atomic_execution_verified=True,
                       intermediate_token_balance_verified=True,
                       rollback_verified=True)
    report["ordered_pair_verified"]=sum(
        r["current_run_atomic_execution_verified"] for r in report["ordered_pairs"])
    report["current_run_ordered_pair_acceptance"]=proof
    report["status"]="CURRENT_RUN_ATOMIC_EVIDENCE_RECONCILED"
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    data=json.loads(Path(args.input).read_text())
    result=reconcile(data)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"ordered_pair_verified":result["ordered_pair_verified"],
                      "ordered_pair_target":result["ordered_pair_target"],
                      "broadcast":False}))

if __name__=="__main__":
    main()
