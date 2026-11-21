import unittest
from unittest.mock import patch
from solders.keypair import Keypair
from arb.orca_swap_v2_atomic_signer_binding import observe_signed_pool_user_binding

RPC = "http://127.0.0.1:8899"
A = "So11111111111111111111111111111111111111112"
B = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

class AtomicSignerBindingTests(unittest.TestCase):
    def test_ephemeral_signer_and_matching_same_context_accounts(self):
        signer = Keypair()
        evidence = {"same_context_pool_user_identities_verified": True,
                    "same_context_vault_mint_programs_verified": True,
                    "user_token_accounts": [A, B],
                    "observation_slot": 101,
                    "observed_balances_base_units": [100, 0]}
        with patch("arb.orca_swap_v2_atomic_signer_binding.observe_atomic_pool_user_identities",
                   return_value=evidence) as observe:
            report = observe_signed_pool_user_binding(RPC, {}, [A, B], signer)
        self.assertEqual(observe.call_args.args[3], str(signer.pubkey()))
        self.assertTrue(report["ephemeral_signer_challenge_verified"])
        self.assertFalse(report["signed_simulation_verified"])
        self.assertFalse(report["actionable"])
        self.assertFalse(report["broadcast"])

    def test_missing_or_mismatched_account_evidence_rejected(self):
        signer = Keypair()
        with patch("arb.orca_swap_v2_atomic_signer_binding.observe_atomic_pool_user_identities",
                   return_value={"same_context_pool_user_identities_verified": True,
                                 "same_context_vault_mint_programs_verified": True,
                                 "user_token_accounts": [B, A]}):
            with self.assertRaises(ValueError):
                observe_signed_pool_user_binding(RPC, {}, [A, B], signer)

    def test_incorrect_signer_type_or_rpc_rejected(self):
        with self.assertRaises(ValueError):
            observe_signed_pool_user_binding(RPC, {}, [A, B], "private key")
        with self.assertRaises(ValueError):
            observe_signed_pool_user_binding("https://api.mainnet-beta.solana.com",
                                             {}, [A, B], Keypair())
