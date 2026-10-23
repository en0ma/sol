import base64
import unittest
from unittest.mock import patch
from arb.signed_standalone_swap_verifier import verify_signed_swap
from arb.token_vaults import TOKEN_PROGRAM

try:
    from solders.keypair import Keypair
    from solders.hash import Hash
    from solders.transaction import Transaction
    from solders.instruction import Instruction
    HAVE_SOLDERS=True
except ImportError:
    HAVE_SOLDERS=False

@unittest.skipUnless(HAVE_SOLDERS,"solders required for signed standalone serialization")
class SignedStandaloneSwapVerifierTests(unittest.TestCase):
    def setUp(self):
        self.payer=Keypair()
        self.program=str(Keypair().pubkey())
        self.input=str(Keypair().pubkey())
        self.output=str(Keypair().pubkey())
        self.mint_in=str(Keypair().pubkey())
        self.mint_out=str(Keypair().pubkey())
        self.wire=bytes(Transaction.new_signed_with_payer(
            [Instruction(Keypair.from_bytes(bytes(self.payer)).pubkey(),b"ignored",[]),
             Instruction(__import__("solders.pubkey",fromlist=["Pubkey"]).Pubkey.from_string(self.program),b"swap",[])],
            self.payer.pubkey(),[self.payer],Hash.default()))

    def args(self):
        return dict(program=self.program,input_account=self.input,
                    output_account=self.output,input_mint=self.mint_in,
                    output_mint=self.mint_out,initial_input=100,initial_output=5,
                    max_input=40,min_output=12)

    def response(self):
        a={"owner":TOKEN_PROGRAM,
           "data":[base64.b64encode(b"token").decode(),"base64"]}
        return {"value":{"err":None,"logs":[
            "Program "+self.program+" invoke [1]",
            "Program "+self.program+" success"],"accounts":[a,a]}}

    def test_signed_positive_deltas_and_floor(self):
        states=[{"mint":self.mint_in,"amount_base_units":72},
                {"mint":self.mint_out,"amount_base_units":19}]
        with patch("arb.signed_standalone_swap_verifier.call",
                   return_value=self.response()) as rpc:
            with patch("arb.signed_standalone_swap_verifier.decode_token_account",
                       side_effect=states):
                result=verify_signed_swap("http://localhost:8899",self.wire,
                                          **self.args())
        self.assertTrue(result["signed_standalone_simulation_verified"])
        self.assertEqual(result["spent_input_base_units"],28)
        self.assertEqual(result["received_output_base_units"],14)
        self.assertFalse(result["broadcast"])
        self.assertTrue(rpc.call_args.args[2][1]["sigVerify"])

    def test_rejects_below_minimum_output(self):
        states=[{"mint":self.mint_in,"amount_base_units":72},
                {"mint":self.mint_out,"amount_base_units":16}]
        with patch("arb.signed_standalone_swap_verifier.call",
                   return_value=self.response()):
            with patch("arb.signed_standalone_swap_verifier.decode_token_account",
                       side_effect=states):
                with self.assertRaisesRegex(ValueError,"constraints"):
                    verify_signed_swap("http://localhost:8899",self.wire,
                                       **self.args())

    def test_tampered_signature_rejected_before_rpc(self):
        wire=bytearray(self.wire)
        wire[1]^=1
        with patch("arb.signed_standalone_swap_verifier.call") as rpc:
            with self.assertRaisesRegex(ValueError,"signature"):
                verify_signed_swap("http://localhost:8899",bytes(wire),
                                   **self.args())
            rpc.assert_not_called()

    def test_wrong_program_rejected_before_rpc(self):
        args=self.args()
        args["program"]=str(Keypair().pubkey())
        with patch("arb.signed_standalone_swap_verifier.call") as rpc:
            with self.assertRaisesRegex(ValueError,"instruction"):
                verify_signed_swap("http://localhost:8899",self.wire,**args)
            rpc.assert_not_called()

    def test_remote_rpc_rejected(self):
        with patch("arb.signed_standalone_swap_verifier.call") as rpc:
            with self.assertRaises(ValueError):
                verify_signed_swap("https://api.mainnet-beta.solana.com",
                                   self.wire,**self.args())
            rpc.assert_not_called()
