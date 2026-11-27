"""Recheck isolated legacy pair packets and actual source-model outputs.

The archived simulation response is not a cryptographically signed RPC
attestation. Recheck packet signatures, compiled order, CPI, token accounts,
and rollback independently of the runner's boolean verdict; keep model
comparison distinct from protocol-exact parity and live profitability.
"""
import base64
from pathlib import Path
import json

from solders.transaction import Transaction
from arb.blockzilla_discovery import SAFE, VENUES, digest, write
from arb.atomic_graph_coordinator import audit_n_leg_cpi, audit_n_leg_balances
from arb.next_ten_signed_atomic_offline import top_level_events
from arb.signed_atomic_instruction_preflight import inspect_signed_legacy_order
from arb.token_vaults import TOKEN_PROGRAM, decode_token_account


def packet(value):
    raw = base64.b64decode(value, validate=True)
    if not 1 <= len(raw) <= 1232:
        raise ValueError("invalid signed legacy packet length")
    tx = Transaction.from_bytes(raw)
    tx.verify()
    if bytes(tx) != raw or len(tx.message.instructions) != 2:
        raise ValueError("noncanonical two-leg packet")
    return tx, raw


def instruction(tx, i):
    ix = tx.message.instructions[i]
    keys = tx.message.account_keys
    return (str(keys[ix.program_id_index]),
            tuple(str(keys[a]) for a in ix.accounts), bytes(ix.data))


def decode_post(response, mints, authority):
    rows = response.get("accounts")
    if not isinstance(rows, list) or len(rows) != 3:
        raise ValueError("positive post accounts missing")
    out = []
    for entry, mint in zip(rows, mints):
        if not isinstance(entry, dict) or entry.get("owner") != TOKEN_PROGRAM:
            raise ValueError("untrusted post token account")
        data = entry.get("data")
        if not isinstance(data, list) or len(data) != 2 or data[1] != "base64":
            raise ValueError("post account encoding")
        token = decode_token_account(base64.b64decode(data[0], validate=True))
        if token["mint"] != mint or token["authority"] != authority:
            raise ValueError("post account identity mismatch")
        out.append(token["amount_base_units"])
    return out


def audit_receipt(receipt, route):
    if any(receipt.get(k) is not False for k in SAFE):
        raise ValueError("unsafe pair receipt")
    if (receipt.get("route_pool_addresses") != route["pools"] or
            receipt.get("route_mints") != route["mints"] or
            [receipt.get("first_venue"), receipt.get("second_venue")] != route["venues"]):
        raise ValueError("pair receipt route mismatch")
    evidence = receipt.get("legacy_pair_audit_evidence")
    if not isinstance(evidence, dict):
        return {"status": "NO_LEGACY_PACKET_EVIDENCE", "packet_audited": False, **SAFE}
    positive, p_raw = packet(evidence["positive_packet_base64"])
    negative, n_raw = packet(evidence["negative_packet_base64"])
    if (str(positive.signatures[0]) != receipt["transaction_signature"] or
            str(positive.signatures[0]) == str(negative.signatures[0]) or
            positive.message.recent_blockhash != negative.message.recent_blockhash or
            list(positive.message.account_keys) != list(negative.message.account_keys)):
        raise ValueError("positive/negative packet context mismatch")
    keys = evidence["ephemeral_token_accounts"]
    authority = evidence["ephemeral_authority"]
    if (not isinstance(keys, list) or len(keys) != 3 or len(set(keys)) != 3 or
            str(positive.message.account_keys[0]) != authority):
        raise ValueError("invalid ephemeral account inventory")
    programs = [VENUES[v][0] for v in route["venues"]]
    for raw in (p_raw, n_raw):
        inspect_signed_legacy_order(raw, *programs, intermediate_account=keys[1])
    for i in range(2):
        a, b = instruction(positive, i), instruction(negative, i)
        if a[0] != programs[i] or a[:2] != b[:2]:
            raise ValueError("negative changed route instruction accounts")
        if route["pools"][i] not in a[1] or not set(keys[i:i+2]) <= set(a[1]):
            raise ValueError("signed pool or token account missing")
        if (i == 0 and a[2] != b[2]) or (i == 1 and a[2] == b[2]):
            raise ValueError("negative must change only second instruction data")
    p_resp, n_resp = evidence["positive_response"], evidence["negative_response"]
    if p_resp.get("err") is not None:
        raise ValueError("positive response error")
    err = n_resp.get("err")
    if not isinstance(err, dict) or err.get("InstructionError", [None])[0] != 1:
        raise ValueError("negative did not fail at second instruction")
    expected = [[programs[0], "invoke"], [programs[0], "success"],
                [programs[1], "invoke"], [programs[1], "success"]]
    if top_level_events(p_resp.get("logs"), set(programs)) != expected:
        raise ValueError("positive program event order")
    expected[-1][1] = "failed"
    if top_level_events(n_resp.get("logs"), set(programs)) != expected:
        raise ValueError("negative program event order")
    amounts = [receipt["declared_first_leg_input_base_units"],
               receipt["declared_second_leg_input_base_units"]]
    before = evidence["persistent_before"]
    post = decode_post(p_resp, route["mints"], authority)
    if (before != [amounts[0], 0, 0] or
            post != receipt["positive_post_balances_base_units"] or
            evidence["persistent_after_negative"] != before):
        raise ValueError("raw balance evidence mismatch")
    cpi = audit_n_leg_cpi(positive, p_resp, keys, amounts)
    balances = audit_n_leg_balances(amounts, before, post,
        rollback_balances=evidence["persistent_after_negative"], later_instruction_failed=True)
    if (cpi["signed_cpi_per_leg_verified"] is not True or
            balances["status"] != "N_LEG_BALANCES_AND_ROLLBACK_RECONCILED"):
        raise ValueError("CPI or balance recheck rejected")
    return {"status": "LEGACY_PAIR_PACKET_AND_RECORDED_SIMULATION_RECHECKED",
        "packet_audited": True, "positive_packet_sha256": digest(p_raw),
        "negative_packet_sha256": digest(n_raw),
        "positive_signature": str(positive.signatures[0]),
        "negative_signature": str(negative.signatures[0]),
        "cpi": cpi, "balances": balances,
        "rpc_response_cryptographically_attested": False,
        "net_profit_verified": False, **SAFE}


def compare_models(fixture, row, receipt):
    """Observe actual exact leg inputs, not inferred route or rounded prices."""
    from arb.fixture_all_venue_signed_quotes import quote_leg
    inputs = [receipt["declared_first_leg_input_base_units"],
              receipt["declared_second_leg_input_base_units"]]
    outputs = [receipt["first_leg_intermediate_received_base_units"],
               receipt["positive_post_balances_base_units"][2]]
    clock = row.get("source_clock")
    if not isinstance(clock, dict) or type(clock.get("unix_timestamp")) is not int:
        raise ValueError("source clock observation unavailable")
    evidence = receipt.get("legacy_pair_audit_evidence") or {}
    before, after = evidence.get("positive_clock_before"), evidence.get("positive_clock_after")
    # Compare source and observed execution timing without claiming the
    # separate sysvar reads prove the exact instruction clock.
    stable_clock = (isinstance(before, dict) and isinstance(after, dict)
        and type(before.get("unix_timestamp")) is int
        and before.get("unix_timestamp") == after.get("unix_timestamp"))
    legs = []
    for index in range(2):
        result = quote_leg(fixture, leg_index=index, amount_in=inputs[index],
                           observed_unix=clock["unix_timestamp"])
        record = {"leg_index": index, "venue": row["venues"][index],
                  "pool": row["pools"][index], "source_slot": row["source_slot"],
                  "actual_signed_input": inputs[index], "actual_signed_output": outputs[index],
                  "quote_status": result.get("quote_status"), "quote_evidence": result,
                  "source_clock": clock, "clock_same_slot": clock.get("slot") == row["source_slot"],
                  "protocol_exact_verified": False}
        prediction = result.get("predicted_output_base_units")
        model = "SOURCE_BOUND_INDICATIVE"
        envelope = result.get("native_fee_envelope")
        if (type(prediction) is not int and record["venue"] == "meteora_dlmm"
                and isinstance(envelope, dict)):
            effective = envelope.get("source_derived_dynamic_fee_quote")
            if isinstance(effective, dict):
                prediction = effective.get("amount_out")
                model = "SOURCE_VOLATILITY_DYNAMIC_FEE_MODELED"
            lo, hi = envelope.get("lower_output_bound"), envelope.get("upper_output_bound")
            if type(lo) is int and type(hi) is int:
                record["fee_envelope_contains_signed_output"] = lo <= outputs[index] <= hi
        if type(prediction) is int and prediction > 0:
            record.update(model=model, modeled_output=prediction,
                          delta_base_units=prediction-outputs[index],
                          exact_sample_amount_match=prediction == outputs[index])
        else:
            record["exact_sample_amount_match"] = None
        legs.append(record)
    return {"status": "SIGNED_LEG_AMOUNT_MODEL_COMPARISON",
            "legs": legs, "source_clock_not_execution_clock": True,
            "positive_clock_before": before, "positive_clock_after": after,
            "positive_clock_timestamp_stable_across_reads": stable_clock,
            "protocol_exact_verified": False, "net_profit_verified": False, **SAFE}


def audit_directory(directory):
    root = Path(directory)
    source = json.loads((root/"pair-source-report.json").read_text())
    signed = json.loads((root/"pair-signed-report.json").read_text())
    if any(report.get(k) is not False for report in (source, signed) for k in SAFE):
        raise ValueError("unsafe reports")
    routes = {r["id"]: r for r in source["routes"]}
    output = {"status": "ISOLATED_PAIR_ARTIFACT_RECHECK", "runner_accepted": 0,
              "packet_and_recorded_simulation_audited": 0, "model_samples": 0,
              "matching_model_samples": 0, "routes": [],
              "excluded_from_primary_inventory": True, "net_profit_verified": False, **SAFE}
    for row in signed["routes"]:
        if row["status"] != "EXISTING_PAIR_RUNNER_SIGNED_ROLLBACK_ACCEPTED":
            continue
        output["runner_accepted"] += 1
        result = {"id": row["id"]}
        output["routes"].append(result)
        try:
            original = routes[row["id"]]
            raw = (root/(row["id"]+"-receipt.json")).read_bytes()
            if digest(raw) != row["receipt_sha256"]:
                raise ValueError("receipt hash mismatch")
            receipt = json.loads(raw)
            result["packet_audit"] = audit_receipt(receipt, original)
            output["packet_and_recorded_simulation_audited"] += int(result["packet_audit"]["packet_audited"])
            comparison_raw = (root/(row["id"]+"-model-comparison.json")).read_bytes()
            if digest(comparison_raw) != row["model_comparison_sha256"]:
                raise ValueError("model evidence hash mismatch")
            comparison = json.loads(comparison_raw)
            result["model_comparison"] = comparison
            for leg in comparison["legs"]:
                if type(leg.get("modeled_output")) is int:
                    output["model_samples"] += 1
                    output["matching_model_samples"] += int(leg["exact_sample_amount_match"] is True)
        except (ValueError, RuntimeError, KeyError, TypeError, OSError) as exc:
            result.update(error_class=type(exc).__name__, diagnostic=str(exc)[:350])
    if output["runner_accepted"] != signed["signed_and_rollback_verified"]:
        raise ValueError("runner count does not reconcile")
    write(root/"pair-independent-audit.json", output)
    return output


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--directory", required=True)
    args = p.parse_args()
    report = audit_directory(args.directory)
    print(json.dumps(report, sort_keys=True))
    if report["packet_and_recorded_simulation_audited"] != report["runner_accepted"]:
        raise SystemExit(2)
