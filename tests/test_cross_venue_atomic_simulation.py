import unittest
from unittest.mock import patch
from arb.cross_venue_atomic_simulation import verify_signed_atomic

A="11111111111111111111111111111111"
B="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

class CrossVenueAtomicSimulationTests(unittest.TestCase):
    def args(self):
        return dict(first_program=A,second_program=B,
                    input_account="input",intermediate_account="middle",
                    output_account="output",input_mint="mint1",
                    intermediate_mint="mint2",output_mint="mint3",
                    initial_input=100,initial_intermediate=0,initial_output=0,
                    max_input=50,minimum_output=1)

    def test_remote_rpc_rejected_before_network(self):
        with patch("arb.cross_venue_atomic_simulation.call") as rpc:
            with self.assertRaises(ValueError):
                verify_signed_atomic("https://api.mainnet-beta.solana.com",b"tx",**self.args())
            rpc.assert_not_called()

    def test_missing_second_program_rejected(self):
        with patch("arb.cross_venue_atomic_simulation.call",return_value={
            "value":{"err":None,"logs":["Program "+A+" invoke [1]","Program "+A+" success"],
                     "accounts":[]}}):
            with self.assertRaisesRegex(ValueError,"missing venue program invocation"):
                verify_signed_atomic("http://127.0.0.1:8899",b"tx",**self.args())

    def test_simulation_error_rejected(self):
        with patch("arb.cross_venue_atomic_simulation.call",return_value={
            "value":{"err":{"InstructionError":[1,"Custom"]},"logs":[]}}):
            with self.assertRaisesRegex(ValueError,"simulation failed"):
                verify_signed_atomic("http://127.0.0.1:8899",b"tx",**self.args())

    def test_duplicate_intermediate_mint_rejected(self):
        args=self.args()
        args["intermediate_mint"]=args["input_mint"]
        with patch("arb.cross_venue_atomic_simulation.call") as rpc:
            with self.assertRaises(ValueError):
                verify_signed_atomic("http://127.0.0.1:8899",b"tx",**args)
            rpc.assert_not_called()
