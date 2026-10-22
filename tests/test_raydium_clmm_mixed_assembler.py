import unittest
from unittest.mock import patch
from arb.mixed_cycle_assembler import assemble_mixed_cycle
from arb.orca_whirlpool import SOL
from arb.venue_capabilities import SWAP_BUILDERS,SIGNED_SWAP_VENUES,ATOMIC_PAIR_EVIDENCE

X="ExampleToken"
route={"tokens":[SOL,X,SOL],"legs":[
    {"venue":"raydium_clmm","pool":"clmm","from":SOL,"to":X},
    {"venue":"raydium_cpmm","pool":"cpmm","from":X,"to":SOL}]}
state={"token_mint_0":SOL,"token_mint_1":X,
       "observation_key":"authenticated-observation",
       "authenticated_tick_arrays":["verified-first","verified-second"]}
cpmm={"token_0_mint":SOL,"token_1_mint":X,
      "token_0_program":"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
      "token_1_program":"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"}
accounts={SOL:"user-sol",X:"user-x"}

class RaydiumClmmAtomicAssemblyTests(unittest.TestCase):
    @patch("arb.mixed_cycle_assembler.build_clmm",return_value="clmm-swap")
    @patch("arb.mixed_cycle_assembler.build_cpmm",return_value="cpmm-swap")
    def test_closed_cycle_directional_clmm_build(self,cp,cl):
        out=assemble_mixed_cycle(route,{"clmm":state,"cpmm":cpmm},
            {"clmm":"authenticated-observation"},accounts,"payer",[100,90],[1,1])
        self.assertEqual(out,["clmm-swap","cpmm-swap"])
        self.assertTrue(cl.call_args.kwargs["input_is_token_0"])
        self.assertEqual(cl.call_args.args[3:5],("user-sol","user-x"))

    @patch("arb.mixed_cycle_assembler.build_clmm")
    def test_missing_authenticated_arrays_rejected(self,cl):
        with self.assertRaisesRegex(ValueError,"authenticated CLMM tick"):
            assemble_mixed_cycle(route,{"clmm":{**state,"authenticated_tick_arrays":[]},"cpmm":cpmm},
                {"clmm":"authenticated-observation"},accounts,"payer",[100,90],[1,1])
        cl.assert_not_called()

    @patch("arb.mixed_cycle_assembler.build_clmm")
    def test_oracle_mismatch_rejected(self,cl):
        with self.assertRaisesRegex(ValueError,"observation mismatch"):
            assemble_mixed_cycle(route,{"clmm":state,"cpmm":cpmm},
                {"clmm":"wrong"},accounts,"payer",[100,90],[1,1])
        cl.assert_not_called()

    def test_builder_support_not_arbitrary_pair_proof(self):
        self.assertEqual(SWAP_BUILDERS,SIGNED_SWAP_VENUES)
        self.assertIn(frozenset(("raydium_clmm","raydium_cpmm")),ATOMIC_PAIR_EVIDENCE)
        self.assertNotIn(frozenset(("raydium_clmm","meteora_dlmm")),ATOMIC_PAIR_EVIDENCE)
