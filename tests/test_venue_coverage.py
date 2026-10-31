import unittest
from arb.venue_coverage import summarize
class VenueCoverageTests(unittest.TestCase):
    def test_pool_decoder_is_not_amount_quote(self):
        report=summarize([{"verified":True,"venue":"raydium_cpmm","address":"p1","mints":["x","y"]}])
        self.assertEqual(report["validated_pools"],1)
        self.assertFalse(report["arb_scanner_profitability_ready"])
        self.assertFalse(report["by_venue"]["raydium_cpmm"]["amount_aware_native_quote"])
        self.assertTrue(report["by_venue"]["meteora_dlmm"]["signed_swap_simulated"])
        self.assertTrue(report["by_venue"]["meteora_dlmm"]["swap_instruction_builder"])
        self.assertFalse(report["by_venue"]["raydium_amm_v4"]["decoder"])
