import base64
import importlib.util
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

    @unittest.skipUnless(importlib.util.find_spec("solders"),
                         "solders required for cryptographically signed transaction")
    def test_signed_structural_order_verified_not_intermediate_consumption(self):
        from solders.keypair import Keypair
        from solders.pubkey import Pubkey
        from solders.instruction import AccountMeta,Instruction
        from solders.transaction import Transaction
        from solders.hash import Hash
        from arb.token_vaults import TOKEN_PROGRAM
        signer=Keypair()
        first,second=Keypair().pubkey(),Keypair().pubkey()
        intermediate=Keypair().pubkey()
        input_account,output_account=Keypair().pubkey(),Keypair().pubkey()
        mints=[str(Keypair().pubkey()) for _ in range(3)]
        accounts=[str(input_account),str(intermediate),str(output_account)]
        meta=AccountMeta(intermediate,False,True)
        instructions=[Instruction(first,b"first",[meta]),
                      Instruction(second,b"second",[meta])]
        wire=bytes(Transaction.new_signed_with_payer(
            instructions,signer.pubkey(),[signer],Hash.default()))
        def token_account():
            return {"owner":TOKEN_PROGRAM,
                    "data":[base64.b64encode(b"account").decode(),"base64"]}
        rpc={"value":{"err":None,"logs":[
            "Program "+str(first)+" invoke [1]",
            "Program "+str(first)+" success",
            "Program "+str(second)+" invoke [1]",
            "Program "+str(second)+" success"],
            "accounts":[token_account() for _ in range(3)]}}
        states=[{"mint":mints[0],"amount_base_units":80},
                {"mint":mints[1],"amount_base_units":0},
                {"mint":mints[2],"amount_base_units":8}]
        with patch("arb.cross_venue_atomic_simulation.call",return_value=rpc) as call:
            with patch("arb.cross_venue_atomic_simulation.decode_token_account",
                       side_effect=states):
                result=verify_signed_atomic(
                    "http://127.0.0.1:8899",wire,
                    first_program=str(first),second_program=str(second),
                    input_account=accounts[0],intermediate_account=accounts[1],
                    output_account=accounts[2],input_mint=mints[0],
                    intermediate_mint=mints[1],output_mint=mints[2],
                    initial_input=100,initial_intermediate=0,initial_output=0,
                    max_input=50,minimum_output=5)
        self.assertTrue(call.call_args.args[2][1]["sigVerify"])
        self.assertTrue(result["instruction_order_verified"])
        self.assertTrue(result["two_venue_invocations_and_terminal_balances_verified"])
        self.assertFalse(result["signed_atomic_simulation_verified"])
        self.assertFalse(result["intermediate_intra_transaction_consumption_verified"])
        self.assertFalse(result["rollback_failure_case_verified"])
        self.assertFalse(result["broadcast"])

    def test_remote_rpc_rejected_before_network(self):
        with patch("arb.cross_venue_atomic_simulation.call") as rpc:
            with self.assertRaises(ValueError):
                verify_signed_atomic("https://api.mainnet-beta.solana.com",b"tx",**self.args())
            rpc.assert_not_called()

    def test_missing_second_program_rejected(self):
        with patch("arb.cross_venue_atomic_simulation.call",return_value={
            "value":{"err":None,"logs":["Program "+A+" invoke [1]","Program "+A+" success"],
                     "accounts":[]}}):
            with self.assertRaisesRegex(ValueError,"venue invocation/success order mismatch"):
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
