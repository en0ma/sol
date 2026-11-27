"""Native archive fallback tests with synthetic packets, not on-chain evidence."""
import json
from pathlib import Path
import tempfile
import unittest

from solders.pubkey import Pubkey
from solders.signature import Signature

from arb import blockzilla_native_archive as n
from arb import blockzilla_discovery as b
from test_blockzilla_discovery import tx_row


class NativeArchiveTests(unittest.TestCase):
    def make_manifest(self, root, records):
        raw = "".join(json.dumps(row) + "\n" for row in records).encode()
        (root / "orca.jsonl").write_bytes(raw)
        n.write(root / "manifest.json", {"schema": 1, "upstream_revision": n.UPSTREAM_REVISION,
            "archive_url": n.ARCHIVE_ROOT + "/epoch-1094", "epoch": 1094,
            "first_block": 0, "blocks_per_venue": 8,
            "venues": {"orca": {"completed": True, "program_id": n.VENUES["orca"][0],
                "dump_sha256": n.digest(raw), "dump_bytes": len(raw),
                "successful_rows": len(n.parse_dump(raw))}}, **n.SAFE})

    def test_parse_rejects_partial_unknown_and_duplicate(self):
        sig = str(Signature.default())
        row = {"signature": sig, "slot": 100, "tx_index": 2, "status": "Succeeded"}
        line = json.dumps(row).encode()
        self.assertEqual(n.parse_dump(line + b"\n"), [row])
        self.assertEqual(n.parse_dump(json.dumps({**row, "status": "Failed"}).encode() + b"\n"), [])
        self.assertEqual(n.parse_dump(json.dumps({**row, "status": "Unknown"}).encode() + b"\n"), [])
        for raw in (line, (line + b"\n") * 2, b"{}\n"):
            with self.assertRaises(ValueError):
                n.parse_dump(raw)

    def test_finalized_membership_and_program_before_hints(self):
        tx, pool = tx_row(True, True)
        sig = b.decode_transaction(tx)["signature"]
        blockhash = str(Pubkey.new_unique())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_manifest(root, [{"signature": sig, "slot": 100,
                                      "tx_index": 1, "status": "Succeeded"}])

            def rpc(_url, method, _params, **_kwargs):
                if method == "getTransaction":
                    return {**tx, "slot": 100}
                if method == "getBlock":
                    return {"blockhash": blockhash, "signatures": [str(Signature.default()), sig]}
                raise AssertionError(method)

            result = n.verify_leads("https://independent.invalid", [], root, rpc_call=rpc)
            self.assertEqual(result["crosschecked_transactions"], 1)
            self.assertEqual(result["crosschecked_blocks"], 1)
            self.assertEqual(result["candidate_hints"][0]["address"], pool)
            self.assertFalse(result["archive_packet_bytes_compared"])
            self.assertFalse(result["broadcast"])
            self.assertEqual(result["independent_rpc_logical_requests"],
                             {"getTransaction": 1, "getBlock": 1})
            self.make_manifest(root, [{"signature": sig, "slot": 100,
                                      "tx_index": 0, "status": "Succeeded"}])
            bad = n.verify_leads("https://independent.invalid", [], root, rpc_call=rpc)
            self.assertEqual(bad["candidate_hints"], [])
            self.assertEqual(bad["crosschecked_blocks"], 0)
            self.make_manifest(root, [{"signature": sig, "slot": 101,
                                      "tx_index": 1, "status": "Succeeded"}])
            bad = n.verify_leads("https://independent.invalid", [], root, rpc_call=rpc)
            self.assertEqual(bad["crosschecked_blocks"], 0)
            self.make_manifest(root, [{"signature": sig, "slot": 100,
                                      "tx_index": 1, "status": "Succeeded"}])
            (root / "orca.jsonl").write_text("{}\n")
            bad = n.verify_leads("https://independent.invalid", [], root, rpc_call=rpc)
            self.assertEqual(bad["independent_rpc_logical_requests"], {})

    def test_round_robin_distinct_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [{"signature": str(Signature.from_bytes(bytes([i]) * 64)), "slot": slot,
                     "tx_index": i, "status": "Succeeded"} for i, slot in ((1, 100), (2, 100), (3, 101))]
            self.make_manifest(root, rows)
            manifest, _ = n.read_manifest(root)
            leads, _, counts = n.sample_leads(root, manifest)
            self.assertEqual([row["slot"] for row in leads], [100, 101])
            self.assertEqual(counts["orca"], 3)


if __name__ == "__main__":
    unittest.main()
