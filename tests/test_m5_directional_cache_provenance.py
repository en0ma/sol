"""Reverse-direction source cache cannot borrow Orca's forward tick arrays."""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arb.m5_four_to_six_source_capture import capture
from arb.orca_whirlpool import PROGRAM as ORCA


class OrderedPoolDirectionCacheTests(unittest.TestCase):
    def test_reversed_mint_route_has_independent_authenticated_evidence(self):
        # Both paths traverse the same three pools in opposite directions.
        # Sorted mint-pair cache keys incorrectly reuse forward arrays.
        rows = [
            [("A", "B", "poolAB"), ("B", "C", "poolBC"), ("C", "A", "poolCA")],
            [("B", "A", "poolAB"), ("A", "C", "poolCA"), ("C", "B", "poolBC")],
        ]
        graph = {
            "status": "SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY",
            "actionable": False, "live_execution_approved": False,
            "broadcast": False,
            "routes": [
                {"hops": 3, "start_mint": legs[0][0],
                 "legs": [{"venue": "orca", "pool": pool,
                           "input": mint_in, "output": mint_out}
                          for mint_in, mint_out, pool in legs]}
                for legs in rows
            ],
        }
        pair_by_pool = {
            "poolAB": ["A", "B"], "poolBC": ["B", "C"],
            "poolCA": ["C", "A"],
        }
        requested_directions = []

        def authenticated_snapshot(rpc, pool, venue):
            self.assertEqual(venue, "orca")
            return {"authenticated": True, "slot": 17,
                    "mints": pair_by_pool[pool]}

        def directional_accounts(rpc, venue, pool, mints, *,
                                 directional_only=False):
            self.assertTrue(directional_only)
            requested_directions.append((pool, tuple(mints)))
            array = f"tick-{pool}-{mints[0]}"
            return [pool, *mints, array], {"tick_arrays": [array]}

        def contextual_accounts(rpc, method, params):
            self.assertEqual(method, "getMultipleAccounts")
            data = []
            for address in params[0]:
                is_pool = address in pair_by_pool
                data.append({
                    "owner": ORCA if is_pool else "source-owner",
                    "executable": False,
                    "lamports": 1,
                    "data": [base64.b64encode(address.encode()).decode(),
                             "base64"],
                })
            return {"context": {"slot": 17}, "value": data}

        def decoded_pool(raw):
            return {
                "token_mint_a": pair_by_pool[raw.decode()][0],
                "token_mint_b": pair_by_pool[raw.decode()][1],
            }

        cache = {}
        with tempfile.TemporaryDirectory() as directory:
            with patch("arb.m5_four_to_six_source_capture.snapshot",
                       side_effect=authenticated_snapshot), patch(
                       "arb.m5_four_to_six_source_capture.venue_accounts",
                       side_effect=directional_accounts), patch(
                       "arb.m5_four_to_six_source_capture.call",
                       side_effect=contextual_accounts), patch(
                       "arb.m5_four_to_six_source_capture.program_data_accounts",
                       return_value={}), patch.dict(
                       "arb.m5_four_to_six_source_capture.DECODERS",
                       {"orca": decoded_pool}):
                capture("http://127.0.0.1:8899", graph, 0,
                        Path(directory) / "forward.json", venue_cache=cache)
                capture("http://127.0.0.1:8899", graph, 1,
                        Path(directory) / "reverse.json", venue_cache=cache)
            import json
            first = json.loads((Path(directory) / "forward.json").read_text())
            second = json.loads((Path(directory) / "reverse.json").read_text())
        self.assertEqual(len(cache), 6)
        self.assertEqual(len(requested_directions), 6)
        self.assertEqual(first["leg_evidence_by_index"][0]["auxiliary"]
                         ["tick_arrays"], ["tick-poolAB-A"])
        self.assertEqual(second["leg_evidence_by_index"][0]["auxiliary"]
                         ["tick_arrays"], ["tick-poolAB-B"])
        self.assertIn("tick-poolAB-B", second["accounts"])
        self.assertNotIn("tick-poolAB-A", second["accounts"])
        self.assertFalse(second["signed_atomic_simulation_verified"])
        self.assertFalse(second["broadcast"])


if __name__ == "__main__":
    unittest.main()
