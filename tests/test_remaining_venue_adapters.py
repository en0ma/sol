import unittest
from unittest.mock import patch
from arb.venue_swap_adapter import build_leg
from arb.next_ten_fork_pool_probe import PROGRAMS,MINT_KEYS
from arb.next_ten_atomic_routes import ALL_42

class MissingVenueAdapterTests(unittest.TestCase):
    def test_seven_programs_and_42_directed_pairs(self):
        self.assertEqual(len(PROGRAMS),7)
        self.assertEqual(len(ALL_42),42)
        self.assertEqual(set(MINT_KEYS),set(PROGRAMS))
    def test_clmm_adapter_preserves_direction_and_exact_input(self):
        st={"token_mint_0":"A","token_mint_1":"B"}
        with patch("arb.raydium_clmm_swap.build",return_value="ix") as build:
            ix=build_leg("raydium_clmm","pool",st,
                {"tick_arrays_authenticated":True,"tick_arrays":["array"]},
                "owner","in","out","B","A",100,1)
        self.assertEqual(ix,"ix")
        self.assertFalse(build.call_args.kwargs["input_is_token_0"])
        self.assertTrue(build.call_args.kwargs["is_base_input"])
    def test_clmm_without_authenticated_ticks_rejected(self):
        with self.assertRaisesRegex(ValueError,"tick arrays unavailable"):
            build_leg("raydium_clmm","p",{"token_mint_0":"A",
                      "token_mint_1":"B"},{},"o","i","d","A","B",100,1)
    def test_amm4_requires_openbook_authentication(self):
        with self.assertRaisesRegex(ValueError,"OpenBook accounts unavailable"):
            build_leg("raydium_amm_v4","p",{"base_mint":"A",
                      "quote_mint":"B"},{},"o","i","d","A","B",100,1)
    def test_amm4_reuses_existing_exact_input_builder(self):
        keys=("amm_authority","market_bids","market_asks","market_event_queue",
              "market_base_vault","market_quote_vault","market_vault_signer")
        proof={"market_accounts_authenticated":True,**{k:k for k in keys}}
        with patch("arb.raydium_amm_v4_swap.build_swap",return_value="ix") as build:
            self.assertEqual(build_leg("raydium_amm_v4","p",
                {"base_mint":"A","quote_mint":"B"},proof,"o","i","d","A","B",100,1),"ix")
        self.assertTrue(build.call_args.kwargs["input_is_base"])
if __name__=="__main__":unittest.main()
