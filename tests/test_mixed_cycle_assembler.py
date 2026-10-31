import unittest
from unittest.mock import patch
from arb.mixed_cycle_assembler import assemble_mixed_cycle
from arb.orca_whirlpool import SOL,USDC
from arb.token_vaults import TOKEN_PROGRAM

RAY="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"
ROUTE={"tokens":[SOL,RAY,USDC,SOL],"legs":[
    {"venue":"orca","pool":"o","from":SOL,"to":RAY},
    {"venue":"raydium_cpmm","pool":"r","from":RAY,"to":USDC},
    {"venue":"orca","pool":"o2","from":USDC,"to":SOL}]}
STATES={
    "o":{"token_mint_a":SOL,"token_mint_b":RAY,"tick_spacing":64,"fee_tier_index_seed":64},
    "r":{"token_0_mint":USDC,"token_1_mint":RAY,
         "token_0_program":TOKEN_PROGRAM,"token_1_program":TOKEN_PROGRAM},
    "o2":{"token_mint_a":SOL,"token_mint_b":USDC,"tick_spacing":64,"fee_tier_index_seed":64}}
ACCOUNTS={SOL:"acct-sol",RAY:"acct-ray",USDC:"acct-usdc"}

class MixedRouteAssemblyTests(unittest.TestCase):
    @patch("arb.mixed_cycle_assembler.build_cpmm",return_value="raydium")
    @patch("arb.mixed_cycle_assembler.build_swap",side_effect=["orca1","orca2"])
    def test_mixed_route_direction_and_accounts(self,orca,cpmm):
        built=assemble_mixed_cycle(ROUTE,STATES,{"o":"oracle1","o2":"oracle2"},
                                   ACCOUNTS,"signer",[100,90,80],[1,1,1])
        self.assertEqual(built,["orca1","raydium","orca2"])
        self.assertFalse(cpmm.call_args.kwargs["input_is_token_0"])
        self.assertEqual(cpmm.call_args.args[3:5],("acct-ray","acct-usdc"))
        self.assertFalse(orca.call_args.kwargs["a_to_b"])
    def test_nonclosing_route_rejected(self):
        bad={**ROUTE,"tokens":[SOL,RAY,USDC,RAY]}
        with self.assertRaisesRegex(ValueError,"close"):
            assemble_mixed_cycle(bad,STATES,{},ACCOUNTS,"signer",[1,1,1],[1,1,1])
    def test_unsupported_venue_rejected(self):
        bad={**ROUTE,"legs":[dict(ROUTE["legs"][0],venue="pumpswap"),*ROUTE["legs"][1:]]}
        with self.assertRaisesRegex(ValueError,"unsupported"):
            assemble_mixed_cycle(bad,STATES,{},ACCOUNTS,"signer",[1,1,1],[1,1,1])

class MeteoraMixedAssemblyTests(unittest.TestCase):
    @patch("arb.mixed_cycle_assembler.build_dlmm",return_value="meteora")
    @patch("arb.mixed_cycle_assembler.build_swap",return_value="orca")
    def test_official_dlmm_leg_uses_verified_directional_mints(self,orca,dlmm):
        route={"tokens":[SOL,RAY,SOL],"legs":[
            {"venue":"orca","pool":"o","from":SOL,"to":RAY},
            {"venue":"meteora_dlmm","pool":"m","from":RAY,"to":SOL}]}
        state=dict(STATES["o"])
        m={"token_x_mint":SOL,"token_y_mint":RAY,"oracle":"verified-oracle",
           "authenticated_bin_arrays":["authenticated-array"],
           "active_bin_array_index":10}
        assembled=assemble_mixed_cycle(
            route,{"o":state,"m":m},{"o":"orca-oracle","m":"verified-oracle"},
            ACCOUNTS,"signer",[100,90],[1,1])
        self.assertEqual(assembled,["orca","meteora"])
        self.assertFalse(dlmm.call_args.kwargs["input_is_x"])
        self.assertEqual(dlmm.call_args.args[3:5],("acct-ray","acct-sol"))
        self.assertFalse(dlmm.call_args.args[1]["input_mint"]==SOL)

    def test_missing_authenticated_bin_arrays_rejected_before_build(self):
        route={"tokens":[SOL,RAY,SOL],"legs":[
            {"venue":"orca","pool":"o","from":SOL,"to":RAY},
            {"venue":"meteora_dlmm","pool":"m","from":RAY,"to":SOL}]}
        m={"token_x_mint":SOL,"token_y_mint":RAY,"oracle":"verified-oracle"}
        with patch("arb.mixed_cycle_assembler.build_swap",return_value="orca"), patch(
            "arb.mixed_cycle_assembler.build_dlmm") as dlmm:
            with self.assertRaisesRegex(ValueError,"authenticated DLMM bin"):
                assemble_mixed_cycle(route,{"o":STATES["o"],"m":m},
                    {"o":"orca-oracle","m":"verified-oracle"},ACCOUNTS,"signer",[100,90],[1,1])
            dlmm.assert_not_called()

class AdaptiveOrcaOracleMutabilityTests(unittest.TestCase):
    @patch("arb.mixed_cycle_assembler.build_cpmm",return_value="cpmm")
    @patch("arb.mixed_cycle_assembler.build_swap",return_value="orca")
    def test_orca_adaptive_fee_requests_writable_oracle(self,orca,cpmm):
        states={**STATES,"o":{**STATES["o"],"tick_spacing":128,"fee_tier_index_seed":64}}
        assemble_mixed_cycle(ROUTE,states,{"o":"oracle1","o2":"oracle2"},
                             ACCOUNTS,"signer",[100,90,80],[1,1,1])
        self.assertTrue(orca.call_args_list[0].kwargs["oracle_writable"])
        self.assertFalse(orca.call_args_list[1].kwargs["oracle_writable"])
