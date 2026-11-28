"""Regression tests for routing, missing jobs and actual evidence reconciliation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from solders.pubkey import Pubkey

from arb import blockzilla_ci_gate as g


def key():
    return str(Pubkey.new_unique())


class BlockzillaGateTests(unittest.TestCase):
    def test_real_cli_writes_github_output_for_both_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report, output = root / "report.json", root / "output"
            for count, status, exit_code, expected in (
                    (0, "NO_CROSSCHECKED_BLOCKS", 2, "false"),
                    (1, "HISTORICAL_HINTS_ONLY", 0, "true")):
                output.write_text("")
                report.write_text(json.dumps({"schema": 1, "status": status,
                    "crosschecked_blocks": count, "candidate_hints": [], **g.SAFE}))
                proc = subprocess.run([sys.executable, "-m", "arb.blockzilla_ci_gate", "route",
                    "--report", str(report), "--exit-code", str(exit_code),
                    "--github-output", str(output)], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(output.read_text(), "usable=" + expected + "\n")
            self.assertRaises(ValueError, g.http_route, json.loads(report.read_text()), 2)
            with self.assertRaises(ValueError):
                g.http_route({"schema": 1, "status": "NO_CROSSCHECKED_BLOCKS",
                    "crosschecked_blocks": 0, "candidate_hints": [{}], **g.SAFE}, 2)

    def test_skipped_or_missing_jobs_fail_closed(self):
        g.check_jobs("success", "true", "skipped", "success")
        g.check_jobs("success", "false", "success", "success")
        for args in (("success", "", "skipped", "skipped"),
                     ("success", "false", "skipped", "skipped"),
                     ("success", "false", "failure", "skipped"),
                     ("success", "true", "skipped", "skipped"),
                     ("failure", "false", "success", "success")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                g.check_jobs(*args)

    def test_actual_evidence_bound_to_source_and_attempts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool, a, b = key(), key(), key()
            hint = {"venue": "orca", "address": pool}
            report = {"schema": 1, "status": "HISTORICAL_HINTS_ONLY",
                      "crosschecked_blocks": 1, "candidate_hints": [hint],
                      "blocks": [{"slot": 100, "crosschecked": True, "sample": {
                          "block_identity_matched": True, "transaction_matched": True}}],
                      **g.SAFE}
            raw = json.dumps(report).encode()
            (root / "historical-hints.json").write_bytes(raw)
            source = {"schema": 1, "status": "SOURCE_AUTHENTICATION_EXPERIMENT",
                "hint_report_sha256": g.digest(raw), "baseline_pool_count": 0,
                "admitted_to_primary_registry": False, "signed_simulation_verified": False,
                "profit_verified": False, "topology_is_hint_level": True,
                "new_source_verified_pools": [{**hint, "mints": [a, b], "source_slot": 102,
                                               "source_verified_only": True}],
                "new_source_verified_pool_count": 1, "new_source_verified_by_venue": {"orca": 1},
                "candidate_attempts": [{**hint, "status": "SOURCE_VERIFIED"}],
                "baseline_topology_starts": 0, "experimental_topology_starts": 0,
                "additional_topology_start_mints": [], **g.SAFE}
            path = root / "source-authentication.json"
            path.write_text(json.dumps(source))
            result = g.check_evidence(root, [], "true")
            self.assertEqual(result["source_verified_pools"], 1)
            self.assertFalse(result["benefit_demonstrated"])
            for bad in ({"hint_report_sha256": "bad"},
                        {"candidate_attempts": []},
                        {"candidate_attempts": [{"venue": "orca", "status": "SOURCE_BATCH_UNAVAILABLE"}]},
                        {"new_source_verified_pool_count": 2},
                        {"signed_simulation_verified": True},
                        {"experimental_topology_starts": 3}):
                path.write_text(json.dumps({**source, **bad}))
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    g.check_evidence(root, [], "true")
            # Native membership is different from HTTP packet comparison.
            report = {**report, "archive_source_mode": "PINNED_COMPACT_V2_PROGRAM_DUMP_PLUS_FINALIZED_RPC",
                      "archive_packet_bytes_compared": False, "crosschecked_transactions": 1,
                      "sample_checks": [{"matched": True, "slot": 100, "signature": "fixture",
                          "scope": "SIGNATURE_SLOT_INDEX_STATUS_AND_PROGRAM"}]}
            raw = json.dumps(report).encode()
            (root / "historical-hints.json").write_bytes(raw)
            path.write_text(json.dumps({**source, "hint_report_sha256": g.digest(raw)}))
            self.assertEqual(g.check_evidence(root, [], "false")["route"], "NATIVE_COMPACT_V2")


if __name__ == "__main__":
    unittest.main()
