import unittest
from unittest.mock import patch
from arb.atomic_cycle_simulation import verify_atomic_cycle
from arb.token_vaults import TOKEN_PROGRAM

TOKENS=[{"address":"a","mint":"So11111111111111111111111111111111111111112","before":100000},
        {"address":"b","mint":"intermediate","before":0}]

class AtomicCycleVerifierTests(unittest.TestCase):
    @patch("arb.atomic_cycle_simulation.call")
    @patch("arb.atomic_cycle_simulation.decode_token_account")
    def test_complete_reconciled_cycle_is_not_automatically_profitable(self,decode,call):
        call.return_value={"value":{"err":None,"logs":[
            "Program first invoke [1]","Program second invoke [1]"],
            "unitsConsumed":110000,"accounts":[
                {"owner":TOKEN_PROGRAM,"data":["AA==","base64"]},
                {"owner":TOKEN_PROGRAM,"data":["AA==","base64"]}]}}
        decode.side_effect=[
            {"mint":TOKENS[0]["mint"],"amount_base_units":100700},
            {"mint":"intermediate","amount_base_units":0}]
        out=verify_atomic_cycle("http://127.0.0.1:8899",b"signed",
                                TOKENS,["first","second"],5000)
        self.assertEqual(out["gross_start_token_base_units"],700)
        self.assertEqual(out["net_after_reference_fee_base_units"],-4300)
        self.assertFalse(out["confirmed_profitable"])
        self.assertTrue(out["intermediates_reconciled"])

    @patch("arb.atomic_cycle_simulation.call")
    @patch("arb.atomic_cycle_simulation.decode_token_account")
    def test_leftover_intermediate_rejected(self,decode,call):
        call.return_value={"value":{"err":None,"logs":[
            "Program first invoke [1]","Program second invoke [1]"],
            "unitsConsumed":10000,"accounts":[
                {"owner":TOKEN_PROGRAM,"data":["AA==","base64"]},
                {"owner":TOKEN_PROGRAM,"data":["AA==","base64"]}]}}
        decode.side_effect=[
            {"mint":TOKENS[0]["mint"],"amount_base_units":100700},
            {"mint":"intermediate","amount_base_units":1}]
        with self.assertRaisesRegex(ValueError,"intermediate"):
            verify_atomic_cycle("http://127.0.0.1:8899",b"signed",
                                TOKENS,["first","second"])

    @patch("arb.atomic_cycle_simulation.call")
    def test_rejects_remote_rpc_before_network(self,call):
        with self.assertRaises(ValueError):
            verify_atomic_cycle("https://mainnet.example",b"signed",
                                TOKENS,["first","second"])
        call.assert_not_called()

    @patch("arb.atomic_cycle_simulation.call")
    def test_transaction_error_rejected(self,call):
        call.return_value={"value":{"err":"InstructionError"}}
        with self.assertRaisesRegex(ValueError,"simulation failed"):
            verify_atomic_cycle("http://127.0.0.1:8899",b"signed",
                                TOKENS,["first","second"])
