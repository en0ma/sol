import unittest
from unittest.mock import patch
from arb.cross_venue_discovery import discover_and_simulate

ORCA = {"address": "orca-pool", "token_mint_a": "So11111111111111111111111111111111111111112",
        "token_mint_b": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"}
RAY = {"token_0_mint": ORCA["token_mint_a"], "token_1_mint": ORCA["token_mint_b"]}

class CrossVenueDiscoveryTests(unittest.TestCase):
    @patch("arb.cross_venue_discovery.run")
    @patch("arb.cross_venue_discovery.verify_vaults")
    @patch("arb.cross_venue_discovery.candidates")
    @patch("arb.cross_venue_discovery.find_pair")
    def test_bounded_verified_routes_stay_nonactionable(self, find, candidates, verify, simulate):
        find.return_value = [ORCA]
        candidates.return_value = {"raydium-pool": RAY}
        verify.return_value = {"verified": True}
        simulate.return_value = {
            "cross_venue_success": True, "residual_usdc_base_units": 0,
            "venues_executed": 2, "net_wsol_change_lamports": 12000,
            "simulation_did_not_persist": True, "signed_simulation_requested": True}
        report = discover_and_simulate("http://127.0.0.1:8899", max_routes=2)
        self.assertEqual(report["routes_tested"], 2)
        self.assertEqual(simulate.call_count, 2)
        self.assertEqual(report["simulated_profitable_candidates"], 2)
        self.assertFalse(report["actionable"])
        self.assertFalse(report["broadcast"])
        self.assertFalse(report["live_execution_approved"])
        self.assertTrue(all(not route["actionable"] for route in report["routes"]))

    @patch("arb.cross_venue_discovery.run")
    @patch("arb.cross_venue_discovery.verify_vaults")
    @patch("arb.cross_venue_discovery.candidates")
    @patch("arb.cross_venue_discovery.find_pair")
    def test_unverified_vault_never_simulated(self, find, candidates, verify, simulate):
        find.return_value = [ORCA]
        candidates.return_value = {"raydium-pool": RAY}
        verify.side_effect = ValueError("unverified")
        report = discover_and_simulate("http://127.0.0.1:8899")
        self.assertEqual(report["routes_tested"], 0)
        simulate.assert_not_called()

    def test_unbounded_routes_rejected(self):
        with self.assertRaises(ValueError):
            discover_and_simulate("http://127.0.0.1:8899", max_routes=100)
