import unittest
from unittest.mock import patch
from arb.next_ten_signed_atomic_offline import run,hydrate
from arb.venue_swap_adapter import build_leg

class SignedNextTenTests(unittest.TestCase):
    def test_mainnet_endpoint_rejected_without_mutation(self):
        with patch("arb.next_ten_signed_atomic_offline.call") as rpc:
            with self.assertRaises(ValueError):
                run("https://api.mainnet-beta.solana.com",{})
            rpc.assert_not_called()
    def test_bad_fixture_never_hydrated(self):
        with patch.dict("os.environ",{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
            with patch("arb.next_ten_signed_atomic_offline.call") as rpc:
                with self.assertRaises(ValueError):
                    hydrate("http://localhost:8899",{"source":"MOCK"})
                rpc.assert_not_called()
    def test_pumpswap_unverified_accounts_fail_closed(self):
        with self.assertRaises(ValueError):
            build_leg("pumpswap","pool",{"base_mint":"x","quote_mint":"y"},{},"owner","a","b",
                      "x","y",100,1)
    def test_dlmm_active_index_must_be_authenticated(self):
        with self.assertRaisesRegex(ValueError,"active bin index required"):
            build_leg("meteora_dlmm","pool",{
                "token_x_mint":"x","token_y_mint":"y",
            },{"bin_arrays":["present"]},"owner","a","b","x","y",100,1)
    def test_positive_amounts_required_before_writes(self):
        with patch("arb.next_ten_signed_atomic_offline.call") as rpc:
            with self.assertRaises(ValueError):
                run("http://localhost:8899",{},amount_in=0)
            rpc.assert_not_called()

if __name__=="__main__":
    unittest.main()
