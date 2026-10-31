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

    @patch("arb.token_cycle_verify.fetch_pool")
    @patch("arb.token_cycle_verify.verify_vaults")
    @patch("arb.token_cycle_verify.decode")
    @patch("arb.token_cycle_verify.call")
    def test_unclassified_raydium_cpmm_is_canonicalized(self, rpc, decode, vaults, fetch):
        from arb.token_cycle_verify import RAYDIUM_PROGRAM
        import base64
        fetch.return_value = {"token_mint_a": SOL, "token_mint_b": USDC}
        rpc.return_value = {"value": {"owner": RAYDIUM_PROGRAM, "executable": False,
                            "data": [base64.b64encode(b"pool").decode(), "base64"]}}
        decode.return_value = {"token_0_mint": SOL, "token_1_mint": USDC}
        vaults.return_value = {"verified": True}
        out = verify_graph("http://127.0.0.1:8899",
                           {"cycles": [cycle("orca", "raydium_unclassified")]})
        result = out["cycles"][0]
        self.assertTrue(result["all_pools_onchain_verified"])
        self.assertEqual(result["legs"][1]["venue"], "raydium_cpmm")
        self.assertEqual(result["legs"][1]["original_venue_hint"], "raydium_unclassified")
        self.assertFalse(result["actionable"])
        self.assertFalse(result["broadcast"])
        self.assertEqual(rpc.call_count, 1)

    @patch("arb.token_cycle_verify.fetch_pool")
    @patch("arb.token_cycle_verify.raydium_clmm.verify")
    @patch("arb.token_cycle_verify.raydium_clmm.decode")
    @patch("arb.token_cycle_verify.call")
    def test_unclassified_raydium_clmm_is_canonicalized(self, rpc, decode, verify, fetch):
        from arb import raydium_clmm
        import base64
        fetch.return_value = {"token_mint_a": SOL, "token_mint_b": USDC}
        rpc.return_value = {"value": {"owner": raydium_clmm.PROGRAM, "executable": False,
                            "data": [base64.b64encode(b"pool").decode(), "base64"]}}
        decode.return_value = {"token_mint_0": SOL, "token_mint_1": USDC}
        result = verify_graph("http://127.0.0.1:8899",
            {"cycles": [cycle("orca", "raydium_unclassified")]})["cycles"][0]
        self.assertTrue(result["all_pools_onchain_verified"])
        self.assertEqual(result["legs"][1]["venue"], "raydium_clmm")
        self.assertEqual(result["legs"][1]["original_venue_hint"], "raydium_unclassified")
        self.assertFalse(result["live_execution_approved"])
        verify.assert_called_once()

    @patch("arb.token_cycle_verify.fetch_pool")
    @patch("arb.token_cycle_verify.meteora_dlmm.verify")
    @patch("arb.token_cycle_verify.meteora_dlmm.decode")
    @patch("arb.token_cycle_verify.call")
    def test_unclassified_meteora_dlmm_is_canonicalized(self, rpc, decode, verify, fetch):
        from arb import meteora_dlmm
        import base64
        fetch.return_value = {"token_mint_a": SOL, "token_mint_b": USDC}
        rpc.return_value = {"value": {"owner": meteora_dlmm.PROGRAM, "executable": False,
                            "data": [base64.b64encode(b"pool").decode(), "base64"]}}
        decode.return_value = {"token_x_mint": SOL, "token_y_mint": USDC}
        result = verify_graph("http://127.0.0.1:8899",
            {"cycles": [cycle("orca", "meteora_unclassified")]})["cycles"][0]
        self.assertTrue(result["all_pools_onchain_verified"])
        self.assertEqual(result["legs"][1]["venue"], "meteora_dlmm")
        self.assertEqual(result["legs"][1]["original_venue_hint"], "meteora_unclassified")
        verify.assert_called_once()

    @patch("arb.token_cycle_verify.fetch_pool")
    @patch("arb.token_cycle_verify.call")
    def test_unclassified_unsupported_owner_fails_closed(self, rpc, fetch):
        import base64
        fetch.return_value = {"token_mint_a": SOL, "token_mint_b": USDC}
        rpc.return_value = {"value": {"owner": "wrong-owner", "executable": False,
                            "data": [base64.b64encode(b"pool").decode(), "base64"]}}
        result = verify_graph("http://127.0.0.1:8899",
            {"cycles": [cycle("orca", "raydium_unclassified")]})["cycles"][0]
        self.assertFalse(result["all_pools_onchain_verified"])
        self.assertEqual(result["legs"][1]["venue"], "raydium_unclassified")
        self.assertIn("unsupported or mismatched", result["rejection_reasons"][0])
        self.assertFalse(result["actionable"])

    @patch("arb.token_cycle_verify.fetch_pool")
    @patch("arb.token_cycle_verify.verify_vaults")
    @patch("arb.token_cycle_verify.decode")
    @patch("arb.token_cycle_verify.call")
    def test_unclassified_verified_owner_wrong_mints_fails_closed(self, rpc, decode, vaults, fetch):
        from arb.token_cycle_verify import RAYDIUM_PROGRAM
        import base64
        fetch.return_value = {"token_mint_a": SOL, "token_mint_b": USDC}
        rpc.return_value = {"value": {"owner": RAYDIUM_PROGRAM, "executable": False,
                            "data": [base64.b64encode(b"pool").decode(), "base64"]}}
        decode.return_value = {"token_0_mint": SOL, "token_1_mint": THIRD}
        vaults.return_value = {"verified": True}
        result = verify_graph("http://127.0.0.1:8899",
            {"cycles": [cycle("orca", "raydium_unclassified")]})["cycles"][0]
        self.assertFalse(result["all_pools_onchain_verified"])
        self.assertIn("on-chain token mints disagree with graph hint", result["rejection_reasons"])
        self.assertEqual(result["legs"][1]["venue"], "raydium_unclassified")

    @patch("arb.token_cycle_verify.verify_vaults")
    @patch("arb.token_cycle_verify.decode")
    @patch("arb.token_cycle_verify.call")
    def test_same_account_different_hints_rejected_after_canonicalization(self, rpc, decode, vaults):
        from arb.token_cycle_verify import RAYDIUM_PROGRAM
        import base64
        rpc.return_value = {"value": {"owner": RAYDIUM_PROGRAM, "executable": False,
                            "data": [base64.b64encode(b"pool").decode(), "base64"]}}
        decode.return_value = {"token_0_mint": SOL, "token_1_mint": USDC}
        vaults.return_value = {"verified": True}
        c = cycle("raydium_cpmm", "raydium_unclassified")
        c["legs"][0]["pool"] = c["legs"][1]["pool"] = "shared-pool"
        result = verify_graph("http://127.0.0.1:8899", {"cycles": [c]})["cycles"][0]
        self.assertFalse(result["all_pools_onchain_verified"])
        self.assertIn("duplicate on-chain pool account in route", result["rejection_reasons"])
        self.assertFalse(result["broadcast"])
