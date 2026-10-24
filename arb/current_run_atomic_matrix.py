"""Current-run ordered venue matrix populated ONLY by accepted real fork artifacts."""
import argparse
import json
from pathlib import Path
from arb.execution_target_matrix import execution_matrix
from arb.damm_cpmm_atomic_evidence_audit import accept, FIRST, SECOND
from arb.cpmm_damm_reverse_evidence_audit import accept_reverse
from arb.next_ten_atomic_evidence import build as audit_ten
from arb.next_ten_atomic_routes import BATCH_10,NEXT_10

def reconcile(evidence, reverse_evidence=None, extra_evidence=None, next_evidence=None):
    report=execution_matrix()
    proof=accept(evidence)
    accepted=proof["verified_ordered_pair_count"]==1
    reverse_proof=accept_reverse(reverse_evidence) if reverse_evidence is not None else None
    reverse_accepted=reverse_proof is not None and reverse_proof["verified_ordered_pair_count"]==1
    ten=audit_ten(extra_evidence or {})
    next_ten=audit_ten(next_evidence or {},batch=NEXT_10)
    accepted_extra={(r["first_venue"],r["second_venue"]) for report in (ten,next_ten) for r in report["routes"] if r["status"]=="VERIFIED"}
    for row in report["ordered_pairs"]:
        matching=(row["first_venue"],row["second_venue"])==(FIRST,SECOND)
        if ((accepted and matching) or (reverse_accepted and (row["first_venue"],row["second_venue"])==(SECOND,FIRST)) or (row["first_venue"],row["second_venue"]) in accepted_extra):
            row.update(this_execution_order_verified=True,
                       current_run_atomic_execution_verified=True,
                       intermediate_token_balance_verified=True,
                       rollback_verified=True)
    report["ordered_pair_verified"]=sum(
        r["current_run_atomic_execution_verified"] for r in report["ordered_pairs"])
    report["current_run_ordered_pair_acceptance"]=proof
    report["current_run_reverse_pair_acceptance"]=reverse_proof
    report["next_ten_independent_acceptance"]=ten
    report["following_ten_independent_acceptance"]=next_ten
    report["status"]="CURRENT_RUN_ATOMIC_EVIDENCE_RECONCILED"
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--reverse-input")
    p.add_argument("--next-ten-evidence-dir")
    p.add_argument("--following-ten-evidence-dir")
    args=p.parse_args()
    data=json.loads(Path(args.input).read_text())
    reverse=json.loads(Path(args.reverse_input).read_text()) if args.reverse_input else None
    extra={}
    if args.next_ten_evidence_dir:
        root=Path(args.next_ten_evidence_dir)
        for first,second in BATCH_10:
            path=root/(first+"__"+second+".json")
            if path.is_file():
                extra[(first,second)]=json.loads(path.read_text())
    following={}
    if args.following_ten_evidence_dir:
        root=Path(args.following_ten_evidence_dir)
        for first,second in NEXT_10:
            path=root/(first+"__"+second+".json")
            if path.is_file():
                following[(first,second)]=json.loads(path.read_text())
    result=reconcile(data,reverse,extra,following)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"ordered_pair_verified":result["ordered_pair_verified"],
                      "ordered_pair_target":result["ordered_pair_target"],
                      "broadcast":False}))

if __name__=="__main__":
    main()
