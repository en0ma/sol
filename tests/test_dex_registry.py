import unittest
from unittest.mock import patch
from arb.dex_registry import probe
from arb.fork_probe import PROGRAMS
class VenueRegistryTests(unittest.TestCase):
    @patch("arb.dex_registry.inspect_account")
    def test_program_only_never_means_pool_ready(self,account):
        account.return_value={"exists":True,"executable":True,"owner_matches":True}
        output=probe("rpc")["venues"]
        self.assertEqual(set(output),{"orca","raydium_cpmm","raydium_clmm",
                                    "meteora_dlmm","meteora_damm_v2"})
        self.assertEqual(output["raydium_clmm"]["status"],"READY_FOR_POOL_VALIDATION")
        self.assertTrue(output["raydium_clmm"]["pool_decoder_available"])
        self.assertFalse(output["raydium_clmm"]["swap_simulator_available"])
        self.assertFalse(output["meteora_dlmm"]["swap_simulator_available"])
        self.assertTrue(output["meteora_dlmm"]["pool_decoder_available"])
        self.assertFalse(output["orca"]["pool_verified"])
        self.assertEqual(account.call_count,len(PROGRAMS))
