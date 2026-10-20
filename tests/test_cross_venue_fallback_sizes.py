import unittest
from unittest.mock import patch
from arb.cross_venue_discovery import pinned_fallback

class MultiSizeFallbackTests(unittest.TestCase):
    @patch("arb.cross_venue_discovery.run")
    @patch("arb.cross_venue_discovery.verify_vaults")
    @patch("arb.cross_venue_discovery.decode")
    @patch("arb.cross_venue_discovery.call")
    @patch("arb.cross_venue_discovery.fetch_pool")
    def test_verified_pair_trades_three_sizes_both_directions(self, fetch, call, decode, vaults, run):
        from arb.orca_whirlpool import SOL, USDC
        from arb.raydium_cpmm import PROGRAM
        fetch.return_value = {"token_mint_a": SOL, "token_mint_b": USDC}
        call.return_value = {"value": {"owner": PROGRAM, "executable": False, "data": ["", "base64"]}}
        decode.return_value = {"token_0_mint": SOL, "token_1_mint": USDC}
        vaults.return_value = {"verified": True}
        def simulate(rpc, orca, ray, max_wsol, size, reverse=False):
            return {"cross_venue_success": True, "venues_executed": 2,
                    "residual_usdc_base_units": 0, "net_wsol_change_lamports": -size,
                    "simulation_did_not_persist": True, "signed_simulation_requested": True}
        run.side_effect = simulate
        result = pinned_fallback("http://127.0.0.1:8899")
        self.assertEqual(result["status"], "PINNED_FALLBACK_COMPLETE")
        self.assertEqual(result["routes_tested"], 6)
        self.assertEqual(set(r["usdc_amount_base_units"] for r in result["routes"]), {1000, 10000, 50000})
        self.assertEqual(result["best_net_wsol_change_lamports"], -1000)
        self.assertEqual(result["simulated_profitable_candidates"], 0)
        self.assertFalse(result["actionable"])
        self.assertFalse(result["broadcast"])
