import unittest
from unittest.mock import patch
from arb.token_cycle_verify import verify_graph
from arb.orca_whirlpool import SOL, USDC

THIRD = "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"

def cycle(a="orca", b="other"):
    return {"tokens": [SOL, USDC, SOL],
            "legs": [{"venue": a, "pool": "orca-pool", "from": SOL, "to": USDC},
                     {"venue": b, "pool": "other-pool", "from": USDC, "to": SOL}]}

class GraphVerifyTests(unittest.TestCase):
    @patch("arb.token_cycle_verify.fetch_pool")
    def test_unsupported_venue_cannot_produce_verified_cycle(self, fetch):
        fetch.return_value = {"token_mint_a": SOL, "token_mint_b": USDC}
        out = verify_graph("http://127.0.0.1:8899", {"cycles": [cycle()]})
        self.assertEqual(out["cycles_with_all_pools_verified"], 0)
        self.assertFalse(out["cycles"][0]["actionable"])
        self.assertFalse(out["cycles"][0]["simulation_verified"])
        self.assertIn("unsupported venue adapter", out["cycles"][0]["rejection_reasons"])

    @patch("arb.token_cycle_verify.fetch_pool")
    def test_mint_mismatch_rejects_pool(self, fetch):
        fetch.return_value = {"token_mint_a": SOL, "token_mint_b": THIRD}
        c = cycle("orca","orca")
        c["legs"][1]["pool"] = "different-orca-pool"
        out = verify_graph("http://127.0.0.1:8899", {"cycles":[c]})
        self.assertEqual(out["cycles_with_all_pools_verified"], 0)

    def test_non_closed_cycle_rejected(self):
        with self.assertRaises(ValueError):
            verify_graph("http://127.0.0.1:8899", {"cycles":[
                {"tokens":[SOL,USDC],"legs":[]} ]})
