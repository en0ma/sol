"""Audit real CPMM↔AMM v4 fixture and signed receipt files from focused CI.

A missing fixture, broken receipt or unsupported source quote becomes an explicit
row, never a fabricated match or CI atomicity failure.
"""
import argparse
import json
from pathlib import Path
from arb.m5_signed_fixture_experiment_report import evaluate, SAFE
from arb.m5_captured_fee_compute_audit import diagnose
from arb.m5_experiment_blocker_summary import summarize

PAIRS = ("raydium_cpmm__raydium_amm_v4", "raydium_amm_v4__raydium_cpmm")

def audit(fixture_dir, receipt_dir, *, observed_unix):
    rows = []
    for pair in PAIRS:
        fixture_path = Path(fixture_dir) / (pair + ".json")
        receipt_path = Path(receipt_dir) / (pair + ".json")
        row = {"route": pair, "status": "UNVERIFIED", "reason_codes": [],
               "quoted_legs": [], "observed_legs": [], "deviation_bps": [],
               "signed_proof_status": "UNVERIFIED", "provenance_status": "UNVERIFIED",
               "net_after_costs": None, **SAFE}
        if not fixture_path.is_file():
            row["reason_codes"].append("SOURCE_FIXTURE_MISSING")
        if not receipt_path.is_file():
            row["reason_codes"].append("SIGNED_RECEIPT_MISSING")
        if not row["reason_codes"]:
            try:
                fixture = json.loads(fixture_path.read_text())
                receipt = json.loads(receipt_path.read_text())
                try:
                    row["captured_fee_and_compute"] = diagnose(fixture, receipt)
                except (ValueError, TypeError, KeyError, OSError, ImportError, ArithmeticError) as exc:
                    row["captured_fee_and_compute"] = {
                        "status": "UNVERIFIED", "reason": "CAPTURED_FEE_COMPUTE_BLOCKED: "+str(exc)[:160],
                        "quote_accuracy_verified": False, "start_mint_fee_cost_verified": False, **SAFE}
                row.update(evaluate(fixture, receipt, observed_unix=observed_unix))
            except (ValueError, TypeError, KeyError, OSError, ImportError, ArithmeticError) as exc:
                row["reason_codes"].append("EXPERIMENT_INPUT_OR_DECODER_BLOCKED: " + str(exc)[:160])
        rows.append(row)
    return {"status": "OFFLINE_DIAGNOSTICS_ONLY", "routes": rows,
            "blocker_summary": summarize(rows),
            "attempted": len(rows),
            "signed_receipts_with_evidence": sum(r["signed_proof_status"] == "VERIFIED" for r in rows),
            "full_intermediate_consumption_observed": sum(
                r.get("full_intermediate_consumption_observed") is True for r in rows),
            "independently_validated_quote_samples": 0,
            "observed_input_quote_probes": sum(
                len(r.get("observed_input_quote_probes", [])) for r in rows),
            "indicative_observed_input_comparisons": sum(
                q.get("status") == "INDICATIVE_OBSERVED_INPUT_COMPARISON"
                for r in rows for q in r.get("observed_input_quote_probes", [])),
            "independent_source_authentication_verified": False,
            "profitability_confirmed": False, **SAFE}

def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--fixture-dir", type=Path, required=True)
    p.add_argument("--receipt-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--observed-unix", type=int, required=True)
    a = p.parse_args(argv)
    report = audit(a.fixture_dir, a.receipt_dir, observed_unix=a.observed_unix)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"attempted": report["attempted"],
                      "independently_validated_quote_samples": 0, **SAFE}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
