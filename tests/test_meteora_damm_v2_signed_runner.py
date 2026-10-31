import unittest
from unittest.mock import patch
from arb.meteora_damm_v2_signed_runner import sign_and_simulate

try:
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction
    from solders.hash import Hash
    HAVE_SOLDERS=True
except ImportError:
    HAVE_SOLDERS=False

@unittest.skipUnless(HAVE_SOLDERS,"solders required for signed DAMM v2 runner")
class DammV2SignedRunnerTests(unittest.TestCase):
    def setUp(self):
        self.payer=Keypair()
        self.pool=str(Keypair().pubkey())
        self.mint_a=str(Keypair().pubkey())
        self.mint_b=str(Keypair().pubkey())
        self.user_a=str(Keypair().pubkey())
        self.user_b=str(Keypair().pubkey())
        self.state={"token_a_mint":self.mint_a,"token_b_mint":self.mint_b,
                    "token_a_vault":str(Keypair().pubkey()),
                    "token_b_vault":str(Keypair().pubkey()),
                    "pool_status":0,"token_a_flag":0,"token_b_flag":0,
                    "liquidity":100,"sqrt_price":100}
        self.evidence={"venue":"meteora_damm_v2","address":self.pool,
                       "slot":100,"vault_base_units":[100,100],
                       "mints":[self.mint_a,self.mint_b]}

    def kwargs(self):
        return dict(pool=self.pool,state=self.state,evidence=self.evidence,
                    payer=self.payer,user_input=self.user_a,
                    user_output=self.user_b,initial_input=100,
                    initial_output=0,amount_in=30,min_amount_out=7,
                    input_is_a=True)

    def test_local_signed_runner_wires_authenticated_pool_and_output_floor(self):
        from arb.meteora_damm_v2 import PROGRAM
        ix=Instruction(Pubkey.from_string(PROGRAM),b"swap",[])
        with patch("arb.meteora_damm_v2_signed_runner.authenticate_pool",
                   return_value={"pool_reauthenticated":True,
                                 "authenticated_slot":102}) as authenticate:
            with patch("arb.meteora_damm_v2_signed_runner.verify_user_accounts") as account_check:
                with patch("arb.meteora_damm_v2_signed_runner.build_swap2",
                           return_value=ix) as builder:
                    with patch("arb.rpc.call",return_value={
                            "value":{"blockhash":str(Hash.default())}}):
                        with patch("arb.meteora_damm_v2_signed_runner.verify_signed_swap",
                                   return_value={"signed_standalone_simulation_verified":True}) as verify:
                            result=sign_and_simulate("http://localhost:8899",**self.kwargs())
        self.assertEqual(authenticate.call_count,1)
        self.assertTrue(result["pool_reauthenticated"])
        self.assertEqual(account_check.call_count,1)
        self.assertTrue(builder.call_args.kwargs["input_is_a"])
        self.assertEqual(verify.call_args.kwargs["max_input"],30)
        self.assertEqual(verify.call_args.kwargs["min_output"],7)
        self.assertEqual(verify.call_args.kwargs["program"],PROGRAM)
        self.assertFalse(result["broadcast"])
        self.assertFalse(result["actionable"])

    def test_real_swap2_builder_serializes_signed_venue_instruction(self):
        from solders.transaction import Transaction
        from arb.meteora_damm_v2 import PROGRAM
        from arb.meteora_damm_v2_swap import SWAP2_DISCRIMINATOR
        with patch("arb.meteora_damm_v2_signed_runner.authenticate_pool",
                   return_value={"pool_reauthenticated":True,"authenticated_slot":103}):
            with patch("arb.meteora_damm_v2_signed_runner.verify_user_accounts"):
                with patch("arb.rpc.call",return_value={
                        "value":{"blockhash":str(Hash.default())}}):
                    with patch("arb.meteora_damm_v2_signed_runner.verify_signed_swap",
                               return_value={"signed_standalone_simulation_verified":True}) as verify:
                        result=sign_and_simulate("http://localhost:8899",**self.kwargs())
        wire=verify.call_args.args[1]
        tx=Transaction.from_bytes(wire)
        tx.verify()
        self.assertEqual(len(tx.message.instructions),1)
        ix=tx.message.instructions[0]
        self.assertEqual(str(tx.message.account_keys[ix.program_id_index]),PROGRAM)
        self.assertEqual(bytes(ix.data[:8]),SWAP2_DISCRIMINATOR)
        self.assertEqual(int.from_bytes(ix.data[8:16],"little"),30)
        self.assertEqual(int.from_bytes(ix.data[16:24],"little"),7)
        self.assertEqual(len(ix.accounts),14)
        self.assertTrue(result["pool_reauthenticated"])
        self.assertFalse(result["broadcast"])

    def test_result_retains_signed_identity_and_fork_evidence(self):
        from solders.transaction import Transaction
        from arb.meteora_damm_v2 import PROGRAM
        with patch("arb.meteora_damm_v2_signed_runner.authenticate_pool",
                   return_value={"pool_reauthenticated":True,
                                 "authenticated_slot":103,
                                 "actionable":False,"live_execution_approved":False,
                                 "broadcast":False}):
            with patch("arb.meteora_damm_v2_signed_runner.verify_user_accounts"):
                with patch("arb.rpc.call",return_value={
                        "value":{"blockhash":str(Hash.default())}}):
                    with patch("arb.meteora_damm_v2_signed_runner.verify_signed_swap",
                               return_value={"signed_standalone_simulation_verified":True,
                                             "spent_input_base_units":30,
                                             "received_output_base_units":10}) as verify:
                        result=sign_and_simulate("http://localhost:8899",**self.kwargs())
        signed=Transaction.from_bytes(verify.call_args.args[1])
        self.assertEqual(result["transaction_signature"],str(signed.signatures[0]))
        self.assertEqual(result["pool"],self.pool)
        self.assertEqual(result["program"],PROGRAM)
        self.assertEqual(result["input_mint"],self.mint_a)
        self.assertEqual(result["output_mint"],self.mint_b)
        self.assertEqual(result["input_account"],self.user_a)
        self.assertEqual(result["output_account"],self.user_b)
        self.assertEqual(result["requested_input_base_units"],30)
        self.assertEqual(result["requested_min_output_base_units"],7)
        self.assertEqual(result["authenticated_slot"],103)
        self.assertFalse(result["actionable"])
        self.assertFalse(result["live_execution_approved"])
        self.assertFalse(result["broadcast"])

    def test_unverified_simulation_cannot_return_successful_runner_result(self):
        with patch("arb.meteora_damm_v2_signed_runner.authenticate_pool",
                   return_value={"pool_reauthenticated":True,"authenticated_slot":103}):
            with patch("arb.meteora_damm_v2_signed_runner.verify_user_accounts"):
                with patch("arb.rpc.call",return_value={
                        "value":{"blockhash":str(Hash.default())}}):
                    with patch("arb.meteora_damm_v2_signed_runner.verify_signed_swap",
                               return_value={"signed_standalone_simulation_verified":False}):
                        with self.assertRaisesRegex(ValueError,"did not verify execution"):
                            sign_and_simulate("http://localhost:8899",**self.kwargs())

    def test_unverified_pool_rejected_without_any_rpc(self):
        kwargs=self.kwargs()
        kwargs["evidence"]={**self.evidence,"address":str(Keypair().pubkey())}
        with patch("arb.meteora_damm_v2_signed_runner.verify_user_accounts") as preflight:
            with self.assertRaisesRegex(ValueError,"authenticated"):
                sign_and_simulate("http://localhost:8899",**kwargs)
            preflight.assert_not_called()

    def test_external_rpc_rejected_without_preflight(self):
        with patch("arb.meteora_damm_v2_signed_runner.verify_user_accounts") as preflight:
            with self.assertRaises(ValueError):
                sign_and_simulate("https://api.mainnet-beta.solana.com",**self.kwargs())
            preflight.assert_not_called()
