"""Reproducible, fail-closed audit of real fixture/receipt pairs.

Consumes existing JSON artifacts only; it never invents evidence, starts a
fork or promotes indicative quotes to independently authenticated pricing.
"""
import argparse
import json
from pathlib import Path
from arb.cpmm_ammv4_signed_experiment import run as quote_experiment
from arb.source_snapshot_manifest import verify

SAFE = {"actionable": False, "live_execution_approved": False, "broadcast": False}

def evaluate(fixture, receipt, *, observed_unix, costs=None):
    result = {
        "status": "UNVERIFIED", "reason_codes": [],
        "source_slot": fixture.get("state_accounts_observed_slot") if isinstance(fixture, dict) else None,
        "route_pools": [fixture.get("first_pool"), fixture.get("second_pool")] if isinstance(fixture, dict) else [],
        "route_venues": [fixture.get("first_venue"), fixture.get("second_venue")] if isinstance(fixture, dict) else [],
        "quoted_legs": [], "observed_legs": [],
        "deviation_bps": [], "signed_proof_status": "UNVERIFIED",
        "provenance_status": "UNVERIFIED", "net_after_costs": None, **SAFE
    }
    if not isinstance(fixture, dict) or not isinstance(receipt, dict):
        result["reason_codes"].append("FIXTURE_OR_RECEIPT_MISSING")
        return result
    try:
        verify(fixture)
    except (ValueError, KeyError, TypeError) as exc:
        result["reason_codes"].append("MANIFEST_INVALID: " + str(exc)[:160])
        return result
    if receipt.get("route_pool_addresses") != result["route_pools"] or receipt.get("route_mints") != fixture.get("route_mints"):
        result["reason_codes"].append("SIGNED_ROUTE_IDENTITY_MISMATCH")
        return result
    initial = receipt.get("initial_balances_base_units")
    final = receipt.get("positive_post_balances_base_units")
    received = receipt.get("first_leg_intermediate_received_base_units")
    if (isinstance(initial, list) and isinstance(final, list) and len(initial) == len(final) == 3
            and all(type(x) is int and x >= 0 for x in initial + final)
            and type(received) is int and received >= 0):
        result["observed_legs"] = [
            {"input": initial[0]-final[0], "output": received},
            {"input": received-(final[1]-initial[1]), "output": final[2]-initial[2]}
        ]
    else:
        result["reason_codes"].append("SIGNED_SPL_BALANCES_UNAVAILABLE")
    amount = result["observed_legs"][0]["input"] if result["observed_legs"] else None
    if type(amount) is not int or amount <= 0:
        result["reason_codes"].append("SIGNED_EXACT_INPUT_UNAVAILABLE")
        return result
    try:
        study = quote_experiment(fixture, receipt, amount_in=amount,
                                 observed_unix=observed_unix,
                                 costs_start_mint_units=costs)
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        result["reason_codes"].append("ACCOUNT_DERIVED_QUOTE_BLOCKED: " + str(exc)[:160])
        return result
    result["quoted_legs"] = [{"input": q["amount_in"], "output": q["amount_out"]} for q in study["quotes"]]
    accuracy = study["accuracy"]
    result["deviation_bps"] = [accuracy["first_leg_deviation_bps"], accuracy["second_leg_deviation_bps"]]
    result["signed_proof_status"] = accuracy["signed_atomic_evidence_status"]
    result["provenance_status"] = accuracy["provenance_status"]
    result["reconciliation_status"] = accuracy["reconciliation_status"]
    risk = study["observed_risk"]
    result["net_after_costs"] = risk.get("observed_net_after_declared_costs_start_mint_units") if risk else None
    if result["observed_legs"][1]["input"] != result["observed_legs"][0]["output"]:
        result["reason_codes"].append("OBSERVED_INTERMEDIATE_UNCONSUMED")
    if result["quoted_legs"][1]["input"] != result["observed_legs"][1]["input"]:
        result["reason_codes"].append("SIGNED_SECOND_LEG_INPUT_DIFFERS_FROM_QUOTE")
    if accuracy["reconciliation_status"] != "RECONCILED_SIGNED_SIMULATION":
        result["reason_codes"].append("QUOTE_AND_SIGNED_OUTPUT_NOT_RECONCILED")
    if accuracy["provenance_status"] != "VERIFIED":
        result["reason_codes"].append("SOURCE_TO_EXECUTION_PROVENANCE_UNVERIFIED")
    # Manifest equality and hydrated readback do not establish independent
    # upstream RPC authenticity; never claim empirical protocol accuracy.
    result["status"] = "DIAGNOSTIC_ONLY"
    return result

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--observed-unix", type=int, required=True)
    parser.add_argument("--costs", type=Path)
    args = parser.parse_args(argv)
    fixture = json.loads(args.fixture.read_text())
    receipt = json.loads(args.receipt.read_text())
    costs = json.loads(args.costs.read_text()) if args.costs else None
    report = evaluate(fixture, receipt, observed_unix=args.observed_unix, costs=costs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "reason_codes": report["reason_codes"], **SAFE}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
