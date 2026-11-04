import unittest
from unittest.mock import patch
from solders.keypair import Keypair
from arb.orca_swap_v2_local_signer_binding import observe_ephemeral_token_pair

RPC="http://127.0.0.1:8899"
MINT_A="So11111111111111111111111111111111111111112"
MINT_B="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TOKEN="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

class LocalSignerBindingTests(unittest.TestCase):
    @patch("arb.orca_swap_v2_local_signer_binding.observe_token_account")
    def test_same_authority_and_slot_binds_without_executing(self,observe):
        signer=Keypair()
        observe.side_effect=[
            {"slot":123,"local_rpc_verified":True},
            {"slot":123,"local_rpc_verified":True}]
        result=observe_ephemeral_token_pair(
            RPC,signer,"account-a",MINT_A,TOKEN,"account-b",MINT_B,TOKEN)
        self.assertEqual(result["authority"],str(signer.pubkey()))
        self.assertTrue(result["token_accounts_verified_same_slot"])
        self.assertFalse(result["signed_simulation_verified"])
        self.assertFalse(result["actionable"])
        self.assertFalse(result["broadcast"])
        self.assertEqual(observe.call_args_list[0].args[3],str(signer.pubkey()))
        self.assertEqual(observe.call_args_list[1].args[3],str(signer.pubkey()))

    @patch("arb.orca_swap_v2_local_signer_binding.observe_token_account")
    def test_slot_divergence_fails_closed(self,observe):
        observe.side_effect=[
            {"slot":123,"local_rpc_verified":True},
            {"slot":124,"local_rpc_verified":True}]
        with self.assertRaisesRegex(ValueError,"slots differ"):
            observe_ephemeral_token_pair(
                RPC,Keypair(),"account-a",MINT_A,TOKEN,"account-b",MINT_B,TOKEN)

    def test_nonlocal_rpc_rejected(self):
        with self.assertRaises(ValueError):
            observe_ephemeral_token_pair(
                "https://rpc.example.com",Keypair(),
                "account-a",MINT_A,TOKEN,"account-b",MINT_B,TOKEN)

if __name__=="__main__":
    unittest.main()
