"""Independent current-run audit of twelve ordered AMM v4 routes only.

Historical 30/42 coverage is displayed as historical, never fresh evidence.
"""
import argparse,json
from pathlib import Path
from arb.next_ten_atomic_routes import ALL_42
from arb.next_ten_atomic_evidence import build

TARGET=tuple(route for route in ALL_42 if "raydium_amm_v4" in route)
assert len(TARGET)==12

def audit(root):
    root=Path(root)
    receipts={}
    for route in TARGET:
        p=root/(route[0]+"__"+route[1]+".json")
        if p.is_file():
            receipts[route]=json.loads(p.read_text())
    r=build(receipts,batch=TARGET)
    return {"status":"FOCUSED_AMM_V4_SIGNED_ATOMIC_AUDIT",
            "current_run_target":12,"current_run_verified":r["batch_verified"],
            "historical_non_amm_v4_verified":30,
            "historical_baseline_run":"https://github.com/en0ma/sol/actions/runs/40134396843",
            "fresh_full_42_verified":False,"routes":r["routes"],
            "broadcast":False,"actionable":False,"live_execution_approved":False}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--receipts",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    result=audit(args.receipts)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"current_run_verified":result["current_run_verified"],
                      "current_run_target":12,"historical_verified":30,
                      "fresh_full_42_verified":False,"broadcast":False}))

if __name__=="__main__":main()
