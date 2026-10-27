import unittest
from unittest.mock import patch
from arb.m5_seven_venue_route_scan import analyze, scan_local_fork, ORDER, SAFE


def snapshot():
    pools = {v: [] for v in ORDER}
    for venue, pool in (("orca", "pool-o"), ("raydium_cpmm", "pool-c")):
        pools[venue].append({"venue": venue, "pool": pool,
            "mints": ["A", "B"], "slot": 123, "authenticated": True, **SAFE})
    return {"source": "READ_ONLY_MAINNET_BACKED_SURFPOOL",
        "authenticated_pools": pools, "failed_pool_checks": [], **SAFE}


class SevenVenueScanner(unittest.TestCase):
    def test_genuine_graph_without_fabricating_quotes_or_signed_proof(self):
        result = analyze(snapshot())
        self.assertEqual(result["authenticated_pool_count"], 2)
        self.assertEqual(result["venue_coverage"]["orca"], 1)
        self.assertEqual(result["venue_coverage"]["raydium_amm_v4"], 0)
        self.assertGreater(result["distinct_venue_cycles"], 0)
        self.assertEqual(result["quoted_candidates"], 0)
        self.assertEqual(result["signed_simulation_attempts"], 0)
        self.assertFalse(result["broadcast"])
        self.assertTrue(all(row["signed_simulation_status"] == "NOT_ATTEMPTED"
                            for row in result["routes"]))

    def test_broad_pool_graph_truncates_with_explicit_nonexhaustive_status(self):
        result=analyze(snapshot(),max_cycles=1)
        self.assertEqual(result["connected_cycles"],1)
        self.assertTrue(result["cycle_inventory_truncated"])
        self.assertFalse(result["cycle_count_is_exhaustive"])
        self.assertEqual(result["cycle_budget"],1)
        self.assertFalse(result["broadcast"])

    def test_each_hop_length_receives_bounded_search_budget(self):
        report=analyze(snapshot(),max_cycles=25)
        self.assertEqual(set(report["cycle_coverage_by_hops"]),set("23456"))
        self.assertEqual(sum(x["budget"] for x in report["cycle_coverage_by_hops"].values()),25)
        self.assertEqual(report["cycle_coverage_by_hops"]["2"]["returned"],4)
        self.assertEqual(report["cycle_coverage_by_hops"]["6"]["returned"],0)

    def test_empty_seven_venue_source_is_explicitly_empty(self):
        report = snapshot()
        report["authenticated_pools"] = {v: [] for v in ORDER}
        result = analyze(report)
        self.assertEqual(result["connected_cycles"], 0)
        self.assertEqual(result["authenticated_pool_count"], 0)

    def test_rejects_missing_venues_and_forged_pool(self):
        source = snapshot()
        del source["authenticated_pools"]["pumpswap"]
        with self.assertRaises(ValueError):
            analyze(source)
        source = snapshot()
        source["authenticated_pools"]["orca"][0]["authenticated"] = False
        with self.assertRaises(ValueError):
            analyze(source)

    def test_rejects_unsafe_metadata(self):
        source = snapshot()
        source["broadcast"] = True
        with self.assertRaises(ValueError):
            analyze(source)

    @patch("arb.m5_seven_venue_route_scan.probe")
    @patch("arb.m5_seven_venue_route_scan.local_rpc_only")
    def test_scan_calls_existing_probe_not_a_competing_engine(self, local, probe):
        probe.return_value = snapshot()
        result = scan_local_fork("http://127.0.0.1:8899", {"pools": []})
        local.assert_called_once()
        self.assertEqual(probe.call_count, 1)
        self.assertEqual(len(probe.call_args.kwargs["batch"]), len(ORDER)*(len(ORDER)-1))
        self.assertEqual(result["authenticated_pool_count"], 2)


if __name__ == "__main__":
    unittest.main()
