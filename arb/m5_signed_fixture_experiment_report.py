"""Reproducible, fail-closed audit of real fixture/receipt pairs.

Consumes existing JSON artifacts only; it never invents evidence, starts a
fork or promotes indicative quotes to independently authenticated pricing.
"""
import argparse
import json
from pathlib import Path
from arb.cpmm_ammv4_signed_experiment import run as quote_experiment
from arb.source_snapshot_manifest import verify
from arb.fixture_config_quote_projection import quote_cpmm_only
from arb.raydium_amm_v4_fixture_quote import quote_from_fixture

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
    if result["observed_legs"]:
        first, second = result["observed_legs"]
        if second["input"] != first["output"]:
            result["reason_codes"].append("OBSERVED_INTERMEDIATE_UNCONSUMED")
            result["intermediate_amount_gap_base_units"] = first["output"] - second["input"]
        else:
            result["intermediate_amount_gap_base_units"] = 0
    result["signed_declared_amounts"] = {
        "first_input": receipt.get("declared_first_leg_input_base_units"),
        "second_input": receipt.get("declared_second_leg_input_base_units"),
        "first_minimum_output": receipt.get("declared_first_leg_minimum_output_base_units"),
        "second_minimum_output": receipt.get("declared_second_leg_minimum_output_base_units")}
    if result["observed_legs"]:
        first, second = result["observed_legs"]
        declared_second = result["signed_declared_amounts"]["second_input"]
        if type(declared_second) is int and declared_second > 0:
            if declared_second != second["input"]:
                result["reason_codes"].append("DECLARED_SECOND_INPUT_VS_SPL_CONSUMPTION_MISMATCH")
            result["second_leg_declared_to_actual_match"] = declared_second == second["input"]
        else:
            result["reason_codes"].append("SIGNED_DECLARED_SECOND_INPUT_UNAVAILABLE")
            result["second_leg_declared_to_actual_match"] = None
        result["full_intermediate_consumption_observed"] = (
            first["output"] > 0 and second["input"] == first["output"])
        if first["output"] <= 0 or second["input"] <= 0:
            result["reason_codes"].append("NONPOSITIVE_SIGNED_LEG_FLOW")
        if second["input"] > first["output"]:
            result["reason_codes"].append("SIGNED_INTERMEDIATE_OVERSPENT")
    amount = result["observed_legs"][0]["input"] if result["observed_legs"] else None
    # Per-leg probes use *observed*, not guessed, signed inputs. They are
    # diagnostics, NOT a matched two-leg quote chain, and cannot validate
    # pricing against a different intermediate amount.
    result["observed_input_quote_probes"] = []
    for i, leg in enumerate(result["observed_legs"]):
        venue = result["route_venues"][i]
        pool = result["route_pools"][i]
        mints = fixture.get("route_mints")
        probe = {"leg_index": i, "venue": venue, "pool": pool,
                 "signed_input": leg["input"], "signed_output": leg["output"],
                 "quote_output": None, "deviation_bps": None,
                 "status": "UNVERIFIED", **SAFE}
        if (not isinstance(mints, list) or len(mints) != 3
                or type(leg["input"]) is not int or leg["input"] <= 0):
            probe["reason"] = "INVALID_SIGNED_LEG_INPUT"
        else:
            try:
                if venue == "raydium_cpmm":
                    edge = {"venue":venue, "pool":pool,
                            "input_mint":mints[i], "output_mint":mints[i+1]}
                    quote = quote_cpmm_only(fixture, observed_unix=observed_unix,
                                            leg=edge, amount_in=leg["input"])["quote"]
                elif venue == "raydium_amm_v4":
                    quote = quote_from_fixture(fixture,pool=pool,input_mint=mints[i],
                         amount_in=leg["input"],observed_unix=observed_unix)["quote"]
                else:
                    raise ValueError("unsupported venue for account-derived probe")
                if (any(quote.get(k) != v for k,v in
                        (("venue",venue),("pool",pool),("input_mint",mints[i]),
                         ("output_mint",mints[i+1]),("amount_in",leg["input"]),
                         ("snapshot_slot",fixture["state_accounts_observed_slot"])))
                        or type(quote.get("amount_out")) is not int
                        or quote["amount_out"] <= 0):
                    raise ValueError("source-bound directional quote identity mismatch")
                probe["quote_output"] = quote["amount_out"]
                probe["deviation_bps"] = abs(quote["amount_out"]-leg["output"])*10000//quote["amount_out"]
                probe["status"] = "INDICATIVE_OBSERVED_INPUT_COMPARISON"
            except (ValueError, KeyError, TypeError, ImportError, ArithmeticError) as exc:
                probe["reason"] = "ACCOUNT_PRICING_BLOCKED: " + str(exc)[:160]
        result["observed_input_quote_probes"].append(probe)
    if type(amount) is not int or amount <= 0:
        result["reason_codes"].append("SIGNED_EXACT_INPUT_UNAVAILABLE")
        return result
    try:
        study = quote_experiment(fixture, receipt, amount_in=amount,
                                 observed_unix=observed_unix,
                                 costs_start_mint_units=costs)
    except (ValueError, KeyError, TypeError, ArithmeticError, ImportError) as exc:
        result["reason_codes"].append("ACCOUNT_DERIVED_QUOTE_BLOCKED: " + str(exc)[:160])
        if "CPMM source fee/reserves unavailable" in str(exc):
            result["reason_codes"].append("CPMM_EFFECTIVE_FEE_OR_RESERVES_UNAVAILABLE")
        return result
    result["quoted_legs"] = [{"input": q["amount_in"], "output": q["amount_out"]} for q in study["quotes"]]
    accuracy = study["accuracy"]
    result["deviation_bps"] = [accuracy["first_leg_deviation_bps"], accuracy["second_leg_deviation_bps"]]
    result["signed_proof_status"] = accuracy["signed_atomic_evidence_status"]
    result["provenance_status"] = accuracy["provenance_status"]
    result["reconciliation_status"] = accuracy["reconciliation_status"]
    risk = study["observed_risk"]
    result["net_after_costs"] = risk.get("observed_net_after_declared_costs_start_mint_units") if risk else None
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
