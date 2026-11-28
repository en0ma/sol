import unittest
from unittest.mock import patch
import base64

from arb.seven_venue_native_execution_quote import (
    quote_signed_single_leg, VENUES)

class NativeExecutionQuoteTests(unittest.TestCase):
    def test_supports_all_seven_native_adapters_without_mainnet_broadcast(self):
        self.assertEqual(VENUES, frozenset((
            "orca","raydium_cpmm","raydium_clmm","meteora_dlmm",
            "meteora_damm_v2","pumpswap","raydium_amm_v4")))
        with self.assertRaises(ValueError):
            quote_signed_single_leg(
                "https://api.mainnet-beta.solana.com",
                venue="orca",pool="p"*44,state={},evidence={},
                signer=object(),input_token_account="a"*44,
                output_token_account="b"*44,input_mint="c"*44,
                output_mint="d"*44,initial_input_base_units=100,
                initial_output_base_units=0,amount_in_base_units=50)

    def test_native_program_signed_poststate_yields_measured_quote_not_profit(self):
        from solders.keypair import Keypair
        from solders.hash import Hash
        from solders.system_program import transfer,TransferParams
        from solders.pubkey import Pubkey
        from arb.token_vaults import TOKEN_PROGRAM
        signer=Keypair()
        ix=transfer(TransferParams(from_pubkey=signer.pubkey(),
                     to_pubkey=Pubkey.new_unique(),lamports=1))
        accounts=[{"owner":TOKEN_PROGRAM,"executable":False,
                   "data":[base64.b64encode(b"token-state").decode(),"base64"]}
                  for _ in range(2)]
        def rpc(_rpc,method,_params=None):
            if method=="getMultipleAccounts":
                return {"context":{"slot":555},"value":accounts}
            if method=="getLatestBlockhash":
                return {"value":{"blockhash":str(Hash.default())}}
            if method=="simulateTransaction":
                self.assertTrue(_params[1]["sigVerify"])
                self.assertFalse(_params[1]["replaceRecentBlockhash"])
                self.assertEqual(_params[1]["minContextSlot"],555)
                return {"value":{"err":None,"unitsConsumed":12345,
                         "logs":["Program "+str(ix.program_id)+" invoke [1]"],
                         "accounts":accounts}}
            raise AssertionError("unexpected RPC method: "+method)
        payer=str(signer.pubkey())
        decoded=[{"mint":"c"*44,"amount_base_units":200,"authority":payer},
                 {"mint":"d"*44,"amount_base_units":3,"authority":payer},
                 {"mint":"c"*44,"amount_base_units":100,"authority":payer},
                 {"mint":"d"*44,"amount_base_units":40,"authority":payer}]
        with patch("arb.seven_venue_native_execution_quote.build_leg",return_value=ix),\
             patch("arb.seven_venue_native_execution_quote.call",side_effect=rpc),\
             patch("arb.seven_venue_native_execution_quote.decode_token_account",
                   side_effect=decoded):
            result=quote_signed_single_leg(
                "http://127.0.0.1:8899",venue="orca",pool="p"*44,
                state={},evidence={},signer=signer,
                input_token_account="a"*44,output_token_account="b"*44,
                input_mint="c"*44,output_mint="d"*44,
                initial_input_base_units=200,initial_output_base_units=3,
                amount_in_base_units=100)
        self.assertEqual(result["original_local_spl_source_slot"],555)
        self.assertEqual(result["amount_in_base_units"],100)
        self.assertEqual(result["amount_out_base_units"],37)
        self.assertTrue(result["native_swap_signed_simulation_verified"])
        self.assertFalse(result["native_math_independently_predicted"])
        self.assertFalse(result["net_profitability_verified"])
        self.assertFalse(result["broadcast"])

    def test_missing_funding_and_unsupported_venue_rejected_before_builder(self):
        args=dict(rpc="http://127.0.0.1:8899",venue="orca",pool="p"*44,
                  state={},evidence={},signer=object(),
                  input_token_account="a"*44,output_token_account="b"*44,
                  input_mint="c"*44,output_mint="d"*44,
                  initial_input_base_units=100,initial_output_base_units=0,
                  amount_in_base_units=101)
        with patch("arb.seven_venue_native_execution_quote.build_leg") as builder:
            with self.assertRaises(ValueError):
                quote_signed_single_leg(**args)
            args.update(amount_in_base_units=99,venue="fake")
            with self.assertRaises(ValueError):
                quote_signed_single_leg(**args)
            builder.assert_not_called()

if __name__=="__main__":
    unittest.main()
