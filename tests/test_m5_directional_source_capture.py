"""Signed route source fixture must request only authenticated required accounts."""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arb.m5_four_to_six_source_capture import capture
from arb.next_ten_pair_fixture_export import venue_accounts


class DirectionalOrcaCaptureTests(unittest.TestCase):
    def test_only_required_direction_arrays_in_multihop_fixture(self):
        pool, mint_a, mint_b = "pool", "A", "B"
        state = {"token_mint_a": mint_a, "token_mint_b": mint_b,
                 "tick_spacing": 64, "fee_tier_index_seed": 64,
                 "tick_current_index": 100,
                 "token_vault_a": "vaultA", "token_vault_b": "vaultB"}
        snapshot = {"mints": [mint_a, mint_b]}
        paths = []

        def arrays(pool_address, tick, spacing, forward):
            paths.append(forward)
            return ["forward1", "forward2", "forward3"] if forward else [
                "backward1", "backward2", "backward3"]

        with patch("arb.next_ten_pair_fixture_export.snapshot",
                   return_value=snapshot), patch(
                   "arb.next_ten_pair_fixture_export._fetch",
                   return_value={pool: {"data": [base64.b64encode(b"state").decode()]}}), patch(
                   "arb.orca_whirlpool.fetch_pool", return_value=state), patch(
                   "arb.whirlpool_swap.select_tick_arrays", side_effect=arrays), patch(
                   "arb.whirlpool_preflight.verify_oracle", return_value="oracle"), patch(
                   "arb.next_ten_pair_fixture_export.call",
                   return_value={"value": None}):
            forward, forward_proof = venue_accounts(
                "http://127.0.0.1:8899", "orca", pool, [mint_a, mint_b],
                directional_only=True)
            reverse, reverse_proof = venue_accounts(
                "http://127.0.0.1:8899", "orca", pool, [mint_b, mint_a],
                directional_only=True)
            legacy, legacy_proof = venue_accounts(
                "http://127.0.0.1:8899", "orca", pool, [mint_a, mint_b])

        self.assertEqual(paths, [True, False, True, False])
        self.assertEqual(set(forward_proof["tick_arrays"]),
                         {"forward1", "forward2", "forward3"})
        self.assertEqual(set(reverse_proof["tick_arrays"]),
                         {"backward1", "backward2", "backward3"})
        self.assertEqual(set(legacy_proof["tick_arrays"]),
                         {"forward1", "forward2", "forward3",
                          "backward1", "backward2", "backward3"})
        self.assertNotIn("backward1", forward)
        self.assertNotIn("forward1", reverse)
        self.assertIn("backward1", legacy)
        self.assertNotIn("oracle", forward)

    def test_missing_required_source_account_fails_with_identity_and_role(self):
        graph = {"status": "SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY",
                 "actionable": False, "live_execution_approved": False,
                 "broadcast": False, "routes": [{
                     "hops": 3, "start_mint": "A",
                     "legs": [
                         {"venue": "orca", "pool": "pool1",
                          "input": "A", "output": "B"},
                         {"venue": "orca", "pool": "pool2",
                          "input": "B", "output": "C"},
                         {"venue": "orca", "pool": "pool3",
                          "input": "C", "output": "A"}]}]}

        def source_proof(rpc, pool, venue):
            pool_mints = {"pool1": ["A", "B"],
                          "pool2": ["B", "C"], "pool3": ["C", "A"]}
            return {"authenticated": True, "slot": 123,
                    "mints": pool_mints[pool]}

        def extras(rpc, venue, pool, mints, *, directional_only=False):
            self.assertTrue(directional_only)
            return [pool, *mints, "missing-array"], {
                "tick_arrays": ["missing-array"]}

        def contextual(rpc, method, params):
            self.assertEqual(method, "getMultipleAccounts")
            values = [{"owner": "any", "executable": False}
                      if address != "missing-array" else None
                      for address in params[0]]
            return {"context": {"slot": 123}, "value": values}

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "fixture.json"
            with patch("arb.m5_four_to_six_source_capture.snapshot",
                       side_effect=source_proof), patch(
                       "arb.m5_four_to_six_source_capture.venue_accounts",
                       side_effect=extras), patch(
                       "arb.m5_four_to_six_source_capture.call",
                       side_effect=contextual):
                with self.assertRaisesRegex(ValueError, "missing-array") as failure:
                    capture("http://127.0.0.1:8899", graph, 0, output)
            self.assertIn("tick_arrays", str(failure.exception))
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
