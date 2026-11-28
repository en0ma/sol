"""Strict evidence acceptance for signed, isolated DAMM v2 fork simulation.

Read-only artifact validation; never signs, calls RPC, or authorizes trading.
A mocked test or merely green GitHub job is not accepted without observed
execution deltas and a program-specific negative-control failure.
"""
import argparse
import json
from pathlib import Path

from arb.meteora_damm_v2 import PROGRAM
from arb.damm_v2_fork_execution import SAFETY

STATUS = "ISOLATED_DAMM_V2_SIGNED_SWAP_VERIFIED"


def audit(record):
    reasons = []
    if not isinstance(record, dict):
        record = {}
        reasons.append("missing evidence object")
    required_true = ("signed_standalone_simulation_verified",
                     "pool_reauthenticated",
                     "positive_and_negative_controls_verified",
                     "negative_slippage_failure_observed",
                     "local_only")
    for key in required_true:
        if record.get(key) is not True:
            reasons.append("missing proof: " + key)
    for key, expected in SAFETY.items():
        if record.get(key) is not expected:
            reasons.append("unsafe or absent: " + key)
    if record.get("status") != STATUS or record.get("venue") != "meteora_damm_v2":
        reasons.append("wrong status or venue")
    if record.get("program") != PROGRAM:
        reasons.append("wrong venue program")
    for key in ("pool", "input_mint", "output_mint", "input_account",
                "output_account", "transaction_signature", "negative_signature"):
        if not isinstance(record.get(key), str) or not record[key]:
            reasons.append("missing identity: " + key)
    if record.get("input_account") == record.get("output_account"):
        reasons.append("same source/destination token account")
    if record.get("input_mint") == record.get("output_mint"):
        reasons.append("same source/destination mint")
    for key in ("authenticated_slot", "fixture_snapshot_slot", "user_snapshot_slot"):
        if type(record.get(key)) is not int or record[key] < 0:
            reasons.append("invalid slot: " + key)
    amount_keys = ("requested_input_base_units", "spent_input_base_units",
                   "received_output_base_units", "requested_min_output_base_units",
                   "min_output_base_units")
    for key in amount_keys:
        if type(record.get(key)) is not int or record[key] <= 0:
            reasons.append("invalid amount: " + key)
    if all(type(record.get(k)) is int for k in amount_keys):
        if not 0 < record["spent_input_base_units"] <= record["requested_input_base_units"]:
            reasons.append("input spent outside requested bound")
        if record["received_output_base_units"] < record["requested_min_output_base_units"]:
            reasons.append("output below requested floor")
        if record["min_output_base_units"] != record["requested_min_output_base_units"]:
            reasons.append("output floor not forwarded")
    if record.get("negative_signature") == record.get("transaction_signature"):
        reasons.append("positive and negative signatures identical")
    logs = record.get("negative_logs")
    if (not isinstance(logs, list)
            or not any(isinstance(l, str) and
                       l.startswith("Program " + PROGRAM + " invoke [") for l in logs)
            or not any(isinstance(l, str) and
                       ("ExceededSlippage" in l or "Exceeded slippage tolerance" in l)
                       for l in logs)):
        reasons.append("program-specific negative slippage logs absent")
    if "6002" not in str(record.get("negative_error", "")):
        reasons.append("DAMM v2 error 6002 absent")
    return {
        "status": "ACCEPTED" if not reasons else "UNVERIFIED",
        "venue": "meteora_damm_v2",
        "signed_standalone_execution_accepted": not reasons,
        "negative_slippage_accepted": not reasons,
        "spent_input_base_units": record.get("spent_input_base_units") if not reasons else None,
        "received_output_base_units": record.get("received_output_base_units") if not reasons else None,
        "failure_reasons": reasons,
        **SAFETY,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = audit(json.loads(Path(args.input).read_text()))
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    if not result["signed_standalone_execution_accepted"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
