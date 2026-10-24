import unittest
from arb.orca_swap_v2_test_signer import prove_ephemeral_signer_control
from solders.pubkey import Pubkey

class EphemeralSignerTests(unittest.TestCase):
    def test_signer_challenge_proves_only_local_possession(self):
        first=prove_ephemeral_signer_control()
        second=prove_ephemeral_signer_control()
        self.assertNotEqual(first["signer_pubkey"],second["signer_pubkey"])
        Pubkey.from_string(first["signer_pubkey"])
        self.assertTrue(first["challenge_signature_verified"])
        self.assertTrue(first["ephemeral_test_key_only"])
        self.assertFalse(first["associated_token_accounts_verified"])
        self.assertFalse(first["fork_slot_verified"])
        self.assertFalse(first["signed_swap_simulation_verified"])
        self.assertFalse(first["actionable"])
        self.assertFalse(first["broadcast"])

if __name__=="__main__":
    unittest.main()
