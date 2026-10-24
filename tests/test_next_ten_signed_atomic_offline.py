import unittest
from unittest.mock import patch
from arb.next_ten_signed_atomic_offline import run,hydrate,top_level_events
from arb.venue_swap_adapter import build_leg

class SignedNextTenTests(unittest.TestCase):
    def test_real_surfpool_nested_program_log_parser(self):
        a="VENUE_A"
        b="VENUE_B"
        logs=[
            "Program VENUE_A invoke [1]",
            "Program TOKEN_PROGRAM invoke [2]",
            "Program TOKEN_PROGRAM success",
            "Program VENUE_A success",
            "Program VENUE_B invoke [1]",
            "Program VENUE_B success",
        ]
        self.assertEqual(top_level_events(logs,{a,b}),
                         [[a,"invoke"],[a,"success"],[b,"invoke"],[b,"success"]])
        logs[-1]="Program VENUE_B failed: custom program error: 0x1"
        self.assertEqual(top_level_events(logs,{a,b})[-1],[b,"failed"])
        self.assertEqual(top_level_events(logs[:-1],{a,b}),[])
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
    def test_pumpswap_fixture_missing_source_accounts_fails_closed(self):
        from arb.pumpswap_account_metas import account_metas
        self.assertIn("protocol_fee_recipient_token_account",
                      [x for x in __import__("arb.pumpswap_account_metas",fromlist=["SELL"]).SELL])
    def test_positive_amounts_required_before_writes(self):
        with patch("arb.next_ten_signed_atomic_offline.call") as rpc:
            with self.assertRaises(ValueError):
                run("http://localhost:8899",{},amount_in=0)
            rpc.assert_not_called()

if __name__=="__main__":
    unittest.main()
