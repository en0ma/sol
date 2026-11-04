"""Reproducible M5 offline market snapshot research report, no external I/O except files.

Snapshot and costs must be provided by trusted upstream producers. JSON inputs
are *not authenticated merely by being read*; this is an indicative replay.
"""
import argparse
import json
from pathlib import Path
from arb.research_trade_size_sweep import sweep

MAX_INPUT_BYTES=2_000_000

def load_json(path):
    if Path(path).stat().st_size>MAX_INPUT_BYTES:
        raise ValueError("oversize M5 input")
    with open(path,encoding="utf-8") as stream:
        return json.load(stream)

def replay(payload):
    if not isinstance(payload,dict):
        raise ValueError("research request must be an object")
    costs=payload.get("costs_start_mint_units")
    if not isinstance(costs,dict):
        raise ValueError("explicit same-start-mint costs required")
    # Static costs are valid only for a deliberately fixed estimate. Reject
    # requests pretending costs are already volume-adaptive.
    if payload.get("costs_vary_by_size") is not False:
        raise ValueError("static cost replay must acknowledge its assumption")
    result=sweep(payload.get("pool_snapshots"),as_of_unix=payload.get("as_of_unix"),
                 input_sizes=payload.get("input_sizes"),
                 cost_provider=lambda route,quotes:costs)
    return {"input_provenance":"CALLER_SUPPLIED_UNVERIFIED_JSON",
            "cost_estimate_assumption":"STATIC_ACROSS_ALL_SIZES",
            "live_market_data_authenticated_by_replay":False,
            "signed_simulation_executed":False,**result}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    report=replay(load_json(args.input))
    Path(args.output).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"sizes_tested":report["sizes_tested"],
                      "candidate_count":report["positive_declared_cost_estimates"],
                      "broadcast":False}))
if __name__=="__main__":
    main()
