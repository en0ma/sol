import unittest
from unittest.mock import patch
from arb.meteora_dlmm import verify as dlmm_verify
from arb.meteora_damm_v2 import verify as damm_verify

class MeteoraSnapshotValidationTests(unittest.TestCase):
    @patch("arb.meteora_dlmm.call")
    def test_dlmm_missing_slot_fails_closed(self,call):
        call.return_value={"value":[None,None,None],"context":{}}
        state={"status":0,"token_mint_x_program_flag":0,"token_mint_y_program_flag":0,
               "reserve_x":"x","reserve_y":"y"}
        with self.assertRaisesRegex(ValueError,"synchronized"):
            dlmm_verify("local","pool",state)

    @patch("arb.meteora_damm_v2.call")
    def test_damm_missing_slot_fails_closed(self,call):
        call.return_value={"value":[None,None,None],"context":{}}
        state={"pool_status":0,"token_a_flag":0,"token_b_flag":0,
               "token_a_vault":"a","token_b_vault":"b"}
        with self.assertRaisesRegex(ValueError,"synchronized"):
            damm_verify("local","pool",state)

    @patch("arb.meteora_dlmm.decode")
    @patch("arb.meteora_dlmm.call")
    def test_dlmm_executable_pool_rejected(self,call,decode):
        call.return_value={"context":{"slot":8},"value":[
            {"owner":"LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
             "executable":True},{"owner":"x"},{"owner":"y"}]}
        state={"status":0,"token_mint_x_program_flag":0,"token_mint_y_program_flag":0,
               "reserve_x":"x","reserve_y":"y"}
        with self.assertRaisesRegex(ValueError,"owner or state"):
            dlmm_verify("local","pool",state)
        decode.assert_not_called()
