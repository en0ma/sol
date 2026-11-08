"""Fail-closed source capture prioritizes real starting mint coverage."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arb.m5_three_hop_atomic_inventory import (
    capture_attempt_order, capture_priority_indices, source_capture,
)


def route(mint, pool):
    return {"start_mint": mint, "hops": 3, "legs": [
        {"venue": "orca", "pool": pool, "output": mint},
        {"venue": "raydium_cpmm", "pool": "cp-" + pool, "output": mint},
        {"venue": "meteora_damm_v2", "pool": "damm-" + pool, "output": mint},
    ]}


class ThreeHopSourceCoverageTests(unittest.TestCase):
    def test_first_mint_pass_precedes_second_attempt(self):
        routes = [route("A", "a1"), route("A", "a2"),
                  route("B", "b1"), route("C", "c1")]
        by_start, starts = capture_priority_indices(routes)
        tried = set()
        captured = set()
        sequence = []
        for _ in range(4):
            index = capture_attempt_order(routes, by_start, starts, captured, tried)
            sequence.append(index)
            tried.add(index)
        self.assertEqual(sequence, [0, 2, 3, 1])

    def test_failed_first_route_retries_same_mint_before_filling(self):
        routes = [route("A", "a1"), route("A", "a2"),
                  route("B", "b1"), route("B", "b2"),
                  route("C", "c1"), route("C", "c2")]
        graph = {"status": "SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY",
                 "routes": routes,
                 "cycle_coverage_by_hops": {"3": {"truncated": False}}}
        attempts = []

        def fake_capture(rpc, graph, index, fixture, *, venue_cache):
            attempts.append(index)
            if index == 0:
                raise ValueError("source account not executable")
            Path(fixture).write_text("{}")

        with tempfile.TemporaryDirectory() as directory:
            with patch("arb.m5_four_to_six_source_capture.capture",
                       side_effect=fake_capture):
                accepted = source_capture("http://127.0.0.1:8899", graph,
                                          directory, target=4)
            report = json.loads((Path(directory) /
                                 "three-hop-inventory.json").read_text())
        # A's first route failed, but A is retried after B and C's
        # first attempts instead of filling the 4-route quota with B/C.
        self.assertEqual(attempts[:4], [0, 2, 4, 1])
        self.assertEqual(len(accepted), 4)
        self.assertEqual(report["selected_graph_start_mints"], 3)
        self.assertEqual(report["source_captured_start_mints"], 3)
        self.assertEqual(report["uncaptured_graph_start_mints"], [])
        self.assertEqual(len(report["blocked_source_routes"]), 1)
        self.assertEqual(report["blocked_source_routes"][0]["source_status"],
                         "CAPTURE_BLOCKED")
        self.assertTrue(all(not r["actionable"] and not r["broadcast"]
                            for r in accepted))

    def test_reverse_orca_cycle_precedes_redundant_forward_captures(self):
        # Pool-identical reverse cycles were near the end of the 200-route
        # candidate graph. They should receive a source-capture attempt
        # before another same-direction route spends the 140-route budget.
        def cycle(first,last,tag):
            return {"start_mint":"A","hops":3,"legs":[
                {"venue":first,"pool":"first-"+tag,"output":"B"},
                {"venue":"raydium_cpmm","pool":"middle-"+tag,"output":"C"},
                {"venue":last,"pool":"last-"+tag,"output":"A"}]}
        routes=[
            cycle("orca","raydium_amm_v4","forward1"),
            cycle("orca","raydium_amm_v4","forward2"),
            cycle("orca","raydium_amm_v4","forward3"),
            cycle("raydium_amm_v4","orca","reverse"),
            route("B","pool-b"),
        ]
        by_start,starts=capture_priority_indices(routes)
        index=capture_attempt_order(routes,by_start,starts,
                                    {"A","B"},{0,4})
        self.assertEqual(index,3)
        self.assertEqual(routes[index]["legs"][-1]["venue"],"orca")
        # Once the reversed direction has been attempted, normal fill may
        # select the remaining forward route. No successful claim is made.
        followup=capture_attempt_order(routes,by_start,starts,
                                       {"A","B"},{0,3,4})
        self.assertEqual(followup,1)

    def test_unseen_reverse_route_does_not_skip_unserved_mint(self):
        def cycle(first,last,tag):
            return {"start_mint":"A","hops":3,"legs":[
                {"venue":first,"pool":tag,"output":"B"},
                {"venue":"raydium_cpmm","pool":tag+"middle","output":"C"},
                {"venue":last,"pool":tag+"last","output":"A"}]}
        rows=[cycle("orca","raydium_amm_v4","forward"),
              cycle("raydium_amm_v4","orca","reverse"),
              route("B","b")]
        by_start,starts=capture_priority_indices(rows)
        self.assertEqual(capture_attempt_order(
            rows,by_start,starts,{"A"},{0}),2)

    def test_source_target_fails_if_no_authenticated_capture(self):
        graph = {"status": "SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY",
                 "routes": [route("A", "a1"), route("B", "b1")]}
        with tempfile.TemporaryDirectory() as directory:
            with patch("arb.m5_four_to_six_source_capture.capture",
                       side_effect=ValueError("unauthenticated")):
                with self.assertRaisesRegex(RuntimeError, "only 0/2"):
                    source_capture("http://127.0.0.1:8899", graph,
                                   directory, target=2)


if __name__ == "__main__":
    unittest.main()
