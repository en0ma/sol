"""Same-window control regressions; synthetic fixtures are not source evidence."""
import json
from pathlib import Path
import tempfile
import unittest

from solders.pubkey import Pubkey
from arb import blockzilla_rpc_comparison as c
from arb import blockzilla_native_archive as n
from test_blockzilla_discovery import tx_row


def key():
    return str(Pubkey.new_unique())


class BlockzillaComparisonTests(unittest.TestCase):
    def test_direct_control_same_sample_budget_and_partial_failure(self):
        row, pool = tx_row(True, True)
        def rpc(_url, method, params, **kwargs):
            self.assertEqual(method, "getBlock")
            self.assertEqual(params[1]["transactionDetails"], "full")
            if params[0] == 101:
                raise RuntimeError("unavailable")
            return {"blockhash": key(), "parentSlot": 99, "transactions": [row]}
        report = c.direct_control("https://rpc.invalid", [], [100, 101], rpc_call=rpc)
        self.assertEqual(report["direct_rpc_blocks_completed"], 1)
        self.assertFalse(report["all_requested_blocks_completed"])
        self.assertEqual(report["independent_rpc_logical_requests"], {"getBlock": 2})
        self.assertEqual(len(report["selected_samples"]), 1)
        self.assertEqual(report["candidate_hints"][0]["address"], pool)
        self.assertGreater(report["successful_rpc_result_json_bytes"]["getBlock"], 0)
        self.assertFalse(report["broadcast"])

    def test_shared_pair_novelty_not_three_hop_claim(self):
        a, b = key(), key()
        baseline = [{"venue": "orca", "address": key(), "mints": [a, b]}]
        pools = [{"venue": "raydium_cpmm", "address": key(), "mints": [b, a]}]
        result = c.coverage(baseline, pools)
        self.assertEqual(result["additional_three_hop_start_mints"], [])
        self.assertEqual(result["additional_cross_venue_pairs"],
                         [{"mints": sorted([a, b]), "venues": ["orca", "raydium_cpmm"]}])
        self.assertTrue(result["topology_is_hint_level"])

    def test_scope_validated_by_manifest_and_epoch(self):
        row, _ = tx_row()
        from arb.blockzilla_discovery import decode_transaction
        sig = decode_transaction(row)["signature"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = [{"slot": 1094*432000, "tx_index": 0, "status": "Succeeded", "signature": sig}]
            raw = (json.dumps(records[0]) + "\n").encode()
            (root / "orca.jsonl").write_bytes(raw)
            n.write(root / "manifest.json", {"schema": 1, "upstream_revision": n.UPSTREAM_REVISION,
                "archive_url": n.ARCHIVE_ROOT+"/epoch-1094", "epoch": 1094,
                "first_block": 0, "blocks_per_venue": 8,
                "venues": {"orca": {"completed": True, "program_id": n.VENUES["orca"][0],
                    "dump_sha256": n.digest(raw), "dump_bytes": len(raw), "successful_rows": 1}},
                **n.SAFE})
            scope = c.archive_scope(root)
            self.assertEqual(scope["slots"], [1094*432000])
            self.assertEqual(len(scope["archive_scope_errors"]), 6)
            self.assertFalse(scope["all_requested_rows_have_successful_venue_records"])
            (root / "orca.jsonl").write_bytes(raw+b"\n")
            with self.assertRaises(ValueError):
                c.archive_scope(root)

    def test_incomplete_control_never_claims_benefit(self):
        scope = {"slots": [100], "manifest_sha256": "fixture", "archive_scope_errors": [],
                 "all_requested_rows_have_successful_venue_records": True}
        hints = {"archive_manifest_sha256": "fixture", "sample_budget_per_venue": 2,
                 "candidate_hints": [], "independent_rpc_logical_requests": {},
                 "elapsed_seconds": 1, "sample_checks": [], **c.SAFE}
        source = {"new_source_verified_pools": [], "source_batch_logical_requests": 0,
                  "candidate_attempts": [], "admitted_to_primary_registry": False,
                  "signed_simulation_verified": False, "profit_verified": False, **c.SAFE}
        control = {"direct_rpc_slots_requested": [100], "selected_samples": [],
                   "all_requested_blocks_completed": False, "blocks": [],
                   "independent_rpc_logical_requests": {"getBlock": 1},
                   "successful_rpc_result_json_bytes": {}}
        result = c.compare(scope, [], hints, source, control, None)
        self.assertEqual(result["status"], "COMPARISON_INCOMPLETE")
        self.assertFalse(result["benefit_demonstrated"])


if __name__ == "__main__":
    unittest.main()
