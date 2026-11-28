"""Reproducible local-only Solana transaction simulation and assertions.

Inputs are serialized signed transactions captured separately, never keys. Transactions
are SIMULATED only, not broadcast. Works with Surfpool fork via SOLANA_RPC_URL.
No DEX HTTP API calls. Use --test for offline fixture parsing tests.
"""
import argparse
import base64
import json
import os
import unittest
from unittest.mock import patch
from arb.rpc import call

def simulate(rpc, case):
    wire=case.get("transaction_base64")
    if not isinstance(wire,str) or not wire:
        raise ValueError("missing transaction bytes")
    try:
        raw=base64.b64decode(wire,validate=True)
    except Exception as e:
        raise ValueError("invalid base64 transaction") from e
    if len(raw)<20 or len(raw)>1232:
        raise ValueError("invalid serialized transaction length")
    programs=case.get("expected_program_logs",[])
    if not isinstance(programs,list) or not all(isinstance(x,str) and x for x in programs):
        raise ValueError("invalid program log assertions")
    result=call(rpc,"simulateTransaction",[wire,{"encoding":"base64","sigVerify":False,
        "replaceRecentBlockhash":True,"commitment":"processed"}],timeout=40)
    value=result.get("value")
    if not isinstance(value,dict):
        raise ValueError("missing simulation result")
    logs=value.get("logs") or []
    err=value.get("err")
    units=value.get("unitsConsumed")
    if not isinstance(logs,list) or any(not isinstance(x,str) for x in logs):
        raise ValueError("malformed simulation logs")
    if units is not None and (type(units) is not int or units<0):
        raise ValueError("invalid compute usage")
    missing=[p for p in programs if not any(("Program "+p+" invoke") in l for l in logs)]
    limit=case.get("max_compute_units",1_400_000)
    if type(limit) is not int or not 1<=limit<=1_400_000:
        raise ValueError("invalid compute limit")
    passed=err is None and not missing and units is not None and units<=limit
    return {"name":case.get("name","unnamed"),"pass":passed,"err":err,
            "unitsConsumed":units,"missingProgramInvocations":missing,"logs":logs}

def run_manifest(rpc,manifest):
    cases=manifest.get("cases")
    if not isinstance(cases,list) or not cases:
        return {"status":"NOT_CONFIGURED","results":[],"passed":False}
    results=[simulate(rpc,c) for c in cases]
    return {"status":"PASS" if all(r["pass"] for r in results) else "FAIL",
            "results":results,"passed":all(r["pass"] for r in results)}

class ReplayTests(unittest.TestCase):
    def test_no_fixtures_not_success(self):
        r=run_manifest("rpc",{"cases":[]})
        self.assertEqual(r["status"],"NOT_CONFIGURED")
        self.assertFalse(r["passed"])

    @patch(__name__+".call")
    def test_program_logs_and_compute(self,mock):
        mock.return_value={"value":{"err":None,"unitsConsumed":3500,
            "logs":["Program Orca111 invoke [1]"]}}
        case={"transaction_base64":base64.b64encode(bytes(100)).decode(),
              "expected_program_logs":["Orca111"],"max_compute_units":5000}
        self.assertTrue(simulate("rpc",case)["pass"])
        case["expected_program_logs"]=["Other111"]
        self.assertFalse(simulate("rpc",case)["pass"])

    @patch(__name__+".call")
    def test_program_error_fails(self,mock):
        mock.return_value={"value":{"err":{"InstructionError":[0,"Custom"]},
            "unitsConsumed":200,"logs":[]}}
        case={"transaction_base64":base64.b64encode(bytes(100)).decode()}
        self.assertFalse(simulate("rpc",case)["pass"])

    def test_bad_input_rejected(self):
        with self.assertRaises(ValueError):
            simulate("rpc",{"transaction_base64":"not-base64"})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",default="arb/replay_cases.json")
    p.add_argument("--output",default="replay-report.json")
    p.add_argument("--test",action="store_true")
    args=p.parse_args()
    if args.test:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(ReplayTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    with open(args.manifest,encoding="utf-8") as f:
        manifest=json.load(f)
    report=run_manifest(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),manifest)
    with open(args.output,"w",encoding="utf-8") as f:
        json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))
    return 0 if report["passed"] else 1

if __name__=="__main__":
    raise SystemExit(main())
