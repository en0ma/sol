"""Isolated quote and signed two-venue trials using Blockzilla-derived pools.

Historical account hints are not pricing or execution evidence. Only novel
identities accepted by the current source verifier may seed these trials.
Reuse the paired source fixture exporter, native quote chain and existing
adaptive signed/rollback runner; do not alter any primary route inventory.
"""
import argparse
import base64
from collections import defaultdict
import json
import os
from pathlib import Path

from arb.blockzilla_discovery import SAFE, VENUES, digest, registry_ids, write
from arb.blockzilla_ci_gate import check_evidence
from arb.pumpswap_local_simulation import local_rpc_only
from arb.source_snapshot_manifest import verify

MAX_ROUTES = 4
AMOUNT = 100000


def choose_pairs(baseline, new_pools, *, maximum=MAX_ROUTES):
    if type(maximum) is not int or not 1 <= maximum <= MAX_ROUTES:
        raise ValueError("invalid isolated pair trial bound")
    old = registry_ids(baseline)
    new = registry_ids(new_pools)
    if old & new or any(p.get("source_verified_only") is not True for p in new_pools):
        raise ValueError("novel source-verified pool identities required")
    groups = defaultdict(list)
    for p in baseline + new_pools:
        if p["venue"] not in VENUES:
            continue
        groups[tuple(sorted(p["mints"]))].append(p)
    candidates = []
    for mints, rows in groups.items():
        for i, a in enumerate(rows):
            for b in rows[i+1:]:
                identities = [(p["venue"], p["address"]) for p in (a, b)]
                novel = sum(identity in new for identity in identities)
                if (not novel or a["venue"] == b["venue"] or a["address"] == b["address"]):
                    continue
                same_observation = (novel == 2 and
                    a.get("historical_observation") is not None and
                    a["historical_observation"] == b.get("historical_observation"))
                candidates.append((novel, same_observation, mints, a, b))
    # Prefer two genuinely new pools, then a shared historical observation.
    # Emit both orderings and both starts before considering another pair.
    candidates.sort(key=lambda x: (-x[0], -int(x[1]), x[2],
                                  x[3]["venue"], x[3]["address"], x[4]["address"]))
    routes = []
    for novel, same_observation, mints, a, b in candidates:
        for start, intermediate in (mints, mints[::-1]):
            for first, second in ((a, b), (b, a)):
                routes.append({"id": f"BZ2-{len(routes)+1:02d}",
                    "venues": [first["venue"], second["venue"]],
                    "pools": [first["address"], second["address"]],
                    "mints": [start, intermediate, start],
                    "novel_pool_count": novel,
                    "novel_pool_identities": [list(k) for k in
                        ((first["venue"], first["address"]), (second["venue"], second["address"]))
                        if k in new],
                    "shared_historical_observation": same_observation, **SAFE})
                if len(routes) >= maximum:
                    return routes
    return routes


def pair_identity(fixture, route):
    verify(fixture)
    if (fixture.get("source") != "READ_ONLY_MAINNET_BACKED_SURFPOOL"
            or any(fixture.get(k) is not False for k in SAFE)
            or [fixture.get("first_venue"), fixture.get("second_venue")] != route["venues"]
            or [fixture.get("first_pool"), fixture.get("second_pool")] != route["pools"]
            or fixture.get("route_mints") != route["mints"]):
        raise ValueError("captured pair fixture identity mismatch")


def prepare(rpc, evidence_dir, directory, baseline, route):
    from arb.next_ten_fork_pool_probe import snapshot, source_clock
    from arb.next_ten_pair_fixture_export import export
    from arb.m5_source_indicative_route_chain import research_chain
    local_rpc_only(rpc)
    root, evidence_dir = Path(directory), Path(evidence_dir)
    root.mkdir(parents=True, exist_ok=True)
    accepted = check_evidence(evidence_dir, baseline, route)
    source_raw = (evidence_dir / "source-authentication.json").read_bytes()
    source = json.loads(source_raw)
    routes = choose_pairs(baseline, source["new_source_verified_pools"])
    report = {"schema": 1, "status": "ISOLATED_BLOCKZILLA_PAIR_SOURCE_TRIALS",
              "historical_source_report_sha256": digest(source_raw),
              "source_evidence_gate": accepted["status"],
              "excluded_from_primary_inventory": True, "routes": routes,
              "source_captured": 0, "indicative_chains_completed": 0,
              "modeled_chains_completed": 0,
              "amount_in_base_units": AMOUNT, **SAFE}
    for row in routes:
        row["capture_status"] = "NOT_CAPTURED"
        row["quote_status"] = "NOT_ATTEMPTED"
        try:
            # Reauthenticate both pools, including any existing registry hint.
            for venue, pool in zip(row["venues"], row["pools"]):
                proof = snapshot(rpc, pool, venue)
                if (proof.get("authenticated") is not True
                        or set(proof.get("mints", [])) != set(row["mints"][:2])):
                    raise ValueError("pair pool reauthentication failed")
            first, second = row["venues"]
            readiness = {"source": "READ_ONLY_MAINNET_BACKED_SURFPOOL",
                "route_candidates": [{"first_venue": first, "second_venue": second,
                    "authenticated_pool_pair_candidates": [{"mint_pair": row["mints"][:2],
                        "first_pool": row["pools"][0], "second_pool": row["pools"][1]}]}]}
            path = root / (row["id"] + "-fixture.json")
            export(rpc, readiness, 0, path, batch=((first, second),))
            fixture = json.loads(path.read_text())
            pair_identity(fixture, row)
            row.update({"capture_status": "CAPTURED", "fixture": path.name,
                        "fixture_sha256": digest(path.read_bytes()),
                        "source_slot": fixture["state_accounts_observed_slot"]})
            report["source_captured"] += 1
            # A separately observed genuine source Clock, not wall-clock
            # timestamp or a claim of same-slot source timing.
            clock = source_clock(rpc)
            row["source_clock"] = clock
            quote = research_chain(fixture, amount_in=AMOUNT,
                                   observed_unix=clock["unix_timestamp"],allow_modeled_dlmm=True)
            quote_path = root / (row["id"] + "-quote.json")
            write(quote_path, quote)
            row["quote_status"] = quote["status"]
            row["quote"] = quote_path.name
            row["quote_sha256"] = digest(quote_path.read_bytes())
            if quote.get("indicative_all_legs") is True:
                report["indicative_chains_completed"] += 1
            if quote.get("modeled_all_legs") is True:
                report["modeled_chains_completed"] += 1
        except (ValueError, RuntimeError, KeyError, TypeError, OSError) as exc:
            row["failure_class"] = type(exc).__name__
            # Only local source errors, no remote RPC credential strings.
            row["diagnostic"] = str(exc)[:350]
        finally:
            write(root / "pair-source-report.json", report)
    write(root / "pair-source-report.json", report)
    return report


def clock_guard(rpc, fixture):
    """Reuse the existing forward-only source-slot clock alignment behavior."""
    from arb.meteora_dlmm import PROGRAM, decode
    from arb.next_ten_fork_pool_probe import source_clock
    from arb.rpc import call
    target = fixture["state_accounts_observed_slot"]
    restricted = []
    for leg in ("first", "second"):
        if fixture[leg + "_venue"] != "meteora_dlmm":
            continue
        pool = fixture[leg + "_pool"]
        record = fixture["accounts"][pool]
        if record.get("owner") != PROGRAM:
            raise ValueError("DLMM pool source owner mismatch")
        state = decode(base64.b64decode(record["data"][0], validate=True))
        if state["pair_type"] != 1:
            continue
        if state["status"] != 0 or state["activation_type"] != 0 or target < state["activation_point"]:
            raise ValueError("unsupported or disabled permissioned DLMM activation")
        restricted.append(pool)
    if not restricted:
        return {"status": "NO_PERMISSIONED_DLMM_CLOCK_ALIGNMENT_REQUIRED"}
    before = source_clock(rpc)
    if before["slot"] < target:
        call(rpc, "surfnet_timeTravel", [{"absoluteSlot": target}])
    after = source_clock(rpc)
    if after["slot"] < target:
        raise ValueError("DLMM offline source slot alignment failed")
    return {"status": "PERMISSIONED_DLMM_SOURCE_SLOT_ALIGNMENT_VERIFIED",
            "source_slot": target, "offline_before": before, "offline_after": after,
            "permissioned_pools": restricted, "timestamp_parity_claimed": False}


def accepted_receipt(receipt, row, fixture):
    from solders.signature import Signature
    required = ("signed_transaction_verified", "instruction_order_verified",
                "signed_atomic_simulation_verified", "intermediate_intra_transaction_consumption_verified",
                "rollback_failure_case_verified", "failed_at_second_instruction_after_successful_first",
                "adaptive_second_input_verified_against_atomic_output",
                "signed_second_leg_consumes_full_first_output")
    if (any(receipt.get(k) is not True for k in required)
            or any(receipt.get(k) is not False for k in SAFE)
            or receipt.get("status") != "SIGNED_ATOMIC_AND_ROLLBACK_VERIFIED"
            or receipt.get("execution_environment") != "ISOLATED_SURFPOOL_OFFLINE"
            or receipt.get("route_pool_addresses") != row["pools"]
            or receipt.get("route_mints") != row["mints"]
            or [receipt.get("first_venue"), receipt.get("second_venue")] != row["venues"]
            or receipt.get("state_account_manifest_sha256") != fixture["state_account_manifest_sha256"]
            or receipt.get("state_accounts_observed_slot") != row["source_slot"]
            or receipt.get("second_leg_failure_instruction_index") != 1
            or receipt.get("declared_first_leg_input_base_units") != AMOUNT):
        return False
    try:
        Signature.from_string(receipt["transaction_signature"])
    except (KeyError, ValueError, TypeError):
        return False
    initial, post = receipt.get("initial_balances_base_units"), receipt.get("positive_post_balances_base_units")
    return (initial == [AMOUNT, 0, 0] and isinstance(post, list) and len(post) == 3
            and all(type(x) is int and x >= 0 for x in post)
            and post[0] == 0 and post[1] == 0 and post[2] > 0
            and receipt.get("negative_persistent_balances_base_units") == initial)


def offline(rpc, directory):
    from arb.next_ten_signed_atomic_offline import run
    local_rpc_only(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE") != "1" or os.environ.get("SURFPOOL_DATASOURCE_RPC_URL"):
        raise ValueError("explicit source-disconnected offline fork required")
    root = Path(directory)
    report = json.loads((root / "pair-source-report.json").read_text())
    if (report.get("status") != "ISOLATED_BLOCKZILLA_PAIR_SOURCE_TRIALS"
            or report.get("excluded_from_primary_inventory") is not True
            or any(report.get(k) is not False for k in SAFE)
            or not isinstance(report.get("routes"), list) or len(report["routes"]) > MAX_ROUTES):
        raise ValueError("invalid isolated pair source report")
    output = {"schema": 1, "status": "ISOLATED_BLOCKZILLA_PAIR_SIGNED_TRIALS",
              "excluded_from_primary_inventory": True, "attempted": 0,
              "signed_and_rollback_verified": 0, "routes": [],
              "net_profit_verified": False, "independent_packet_bytes_audited": False, **SAFE}
    programs = {}
    for row in report["routes"]:
        result = {k: row[k] for k in ("id", "venues", "pools", "mints", "novel_pool_identities")}
        output["routes"].append(result)
        result["status"] = "SOURCE_NOT_CAPTURED"
        if row.get("capture_status") != "CAPTURED":
            continue
        output["attempted"] += 1
        try:
            raw = (root / (row["id"] + "-fixture.json")).read_bytes()
            if digest(raw) != row["fixture_sha256"]:
                raise ValueError("source fixture hash mismatch")
            fixture = json.loads(raw)
            pair_identity(fixture, row)
            result["offline_clock_alignment"] = clock_guard(rpc, fixture)
            receipt = run(rpc, fixture, amount_in=AMOUNT, amount_intermediate=1,
                          batch=(tuple(row["venues"]),), adaptive_all_venues=True,
                          program_cache=programs, retain_legacy_audit_evidence=True)
            path = root / (row["id"] + "-receipt.json")
            write(path, receipt)
            result["receipt"] = path.name
            result["receipt_sha256"] = digest(path.read_bytes())
            result["receipt_status"] = receipt.get("status")
            if accepted_receipt(receipt, row, fixture):
                result.update({"status": "EXISTING_PAIR_RUNNER_SIGNED_ROLLBACK_ACCEPTED",
                    "signature": receipt["transaction_signature"],
                    "observed_gross_delta_start_mint_base_units":
                        receipt["positive_post_balances_base_units"][2] - AMOUNT,
                    "net_profit_verified": False})
                if row.get("quote"):
                    qraw = (root / (row["id"] + "-quote.json")).read_bytes()
                    if digest(qraw) != row["quote_sha256"]:
                        raise ValueError("quote evidence hash mismatch")
                    quote = json.loads(qraw)
                    if quote.get("indicative_all_legs") is True:
                        result["indicative_gross_delta_start_mint_base_units"] = quote["gross_delta_start_mint_base_units"]
                from arb.blockzilla_pair_evidence import compare_models
                try:
                    comparison = compare_models(fixture, row, receipt)
                    model_path = root / (row["id"] + "-model-comparison.json")
                    write(model_path, comparison)
                    result["model_comparison_sha256"] = digest(model_path.read_bytes())
                except (ValueError, RuntimeError, KeyError, TypeError, OSError) as exc:
                    result["model_comparison_error"] = type(exc).__name__
                output["signed_and_rollback_verified"] += 1
            else:
                result["status"] = "SIGNED_OR_ROLLBACK_NOT_ACCEPTED"
        except (ValueError, RuntimeError, KeyError, TypeError, OSError) as exc:
            result.update({"status": "PREPARATION_OR_SIMULATION_BLOCKED",
                           "error_class": type(exc).__name__, "diagnostic": str(exc)[:350]})
        finally:
            write(root / "pair-signed-report.json", output)
    write(root / "pair-signed-report.json", output)
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase", choices=("source", "offline"), required=True)
    p.add_argument("--directory", required=True)
    p.add_argument("--evidence-directory")
    p.add_argument("--route", choices=("true", "false"))
    p.add_argument("--registry", default="arb/pool_registry.json")
    args = p.parse_args()
    if args.phase == "source":
        baseline = json.loads(Path(args.registry).read_text())["pools"]
        result = prepare("http://127.0.0.1:8899", args.evidence_directory,
                         args.directory, baseline, args.route)
    else:
        result = offline("http://127.0.0.1:8899", args.directory)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
