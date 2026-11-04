import unittest
from unittest.mock import patch
from arb.token_cycle_verify import verify_graph
from arb.orca_whirlpool import SOL, USDC
from arb import raydium_clmm, meteora_dlmm

def graph(venue):
    return {"cycles":[{"tokens":[SOL,USDC,SOL],
        "legs":[{"venue":venue,"pool":"pool1","from":SOL,"to":USDC},
                {"venue":venue,"pool":"pool2","from":USDC,"to":SOL}]}]}

class OwnerClassifyTests(unittest.TestCase):
    @patch("arb.token_cycle_verify.raydium_clmm.verify")
    @patch("arb.token_cycle_verify.raydium_clmm.decode")
    @patch("arb.token_cycle_verify.call")
    def test_unclassified_raydium_clmm_verified_by_owner_and_vaults(self, rpc, decode, verify):
        rpc.return_value={"value":{"owner":raydium_clmm.PROGRAM,"executable":False,
                                   "data":["AA==","base64"]}}
        decode.return_value={"token_mint_0":SOL,"token_mint_1":USDC}
        out=verify_graph("http://127.0.0.1:8899",graph("raydium_unclassified"))
        self.assertEqual(out["cycles_with_all_pools_verified"],1)
        self.assertFalse(out["actionable"])
        self.assertFalse(out["cycles"][0]["simulation_verified"])
        self.assertEqual(verify.call_count,2)

    @patch("arb.token_cycle_verify.meteora_dlmm.verify")
    @patch("arb.token_cycle_verify.meteora_dlmm.decode")
    @patch("arb.token_cycle_verify.call")
    def test_unclassified_meteora_dlmm_verified_by_owner(self,rpc,decode,verify):
        rpc.return_value={"value":{"owner":meteora_dlmm.PROGRAM,"executable":False,
                                   "data":["AA==","base64"]}}
        decode.return_value={"token_x_mint":SOL,"token_y_mint":USDC}
        out=verify_graph("http://127.0.0.1:8899",graph("meteora_unclassified"))
        self.assertEqual(out["cycles_with_all_pools_verified"],1)
        self.assertEqual(verify.call_count,2)

    @patch("arb.token_cycle_verify.call")
    def test_wrong_program_owner_cannot_claim_verified(self,rpc):
        rpc.return_value={"value":{"owner":"wrong","executable":False,
                                   "data":["AA==","base64"]}}
        out=verify_graph("http://127.0.0.1:8899",graph("raydium_unclassified"))
        self.assertEqual(out["cycles_with_all_pools_verified"],0)
