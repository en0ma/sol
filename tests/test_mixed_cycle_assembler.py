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
    "o":{"token_mint_a":SOL,"token_mint_b":RAY},
    "r":{"token_0_mint":USDC,"token_1_mint":RAY,
         "token_0_program":TOKEN_PROGRAM,"token_1_program":TOKEN_PROGRAM},
    "o2":{"token_mint_a":SOL,"token_mint_b":USDC}}
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
        bad={**ROUTE,"legs":[dict(ROUTE["legs"][0],venue="meteora_dlmm"),*ROUTE["legs"][1:]]}
        with self.assertRaisesRegex(ValueError,"unsupported"):
            assemble_mixed_cycle(bad,STATES,{},ACCOUNTS,"signer",[1,1,1],[1,1,1])
