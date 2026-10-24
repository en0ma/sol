"""Independent full 42 ordered pair evidence audit, with honest missing-pair gaps."""
import argparse
import json
from pathlib import Path
from arb.next_ten_atomic_routes import ALL_42
from arb.next_ten_atomic_evidence import assess

def reconcile_forty_two(receipts):
    if not isinstance(receipts,dict) or set(receipts)-set(ALL_42):
        raise ValueError("invalid ordered atomic receipt inventory")
    routes=[assess(pair,receipts.get(pair)) for pair in ALL_42]
    verified=sum(r["status"]=="VERIFIED" for r in routes)
    return {"status":"INDEPENDENT_42_PAIR_SIGNED_ATOMIC_AUDIT",
            "ordered_pair_target":42,"ordered_pair_verified":verified,
            "ordered_pair_missing_or_unverified":42-verified,
            "routes":routes,"actionable":False,
            "live_execution_approved":False,"broadcast":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--evidence-dirs",nargs="+",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    receipts={}
    for directory in args.evidence_dirs:
        folder=Path(directory)
        for first,second in ALL_42:
            file=folder/(first+"__"+second+".json")
            if file.exists():
                key=(first,second)
                value=json.loads(file.read_text())
                # No last-writer-wins: repeated route evidence must not
                # silently overwrite a failed or contradictory receipt.
                if key in receipts and receipts[key]!=value:
                    raise ValueError("conflicting directional route receipts")
                receipts[key]=value
    report=reconcile_forty_two(receipts)
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"verified":report["ordered_pair_verified"],"target":42,
                      "broadcast":False}))

if __name__=="__main__":
    main()
