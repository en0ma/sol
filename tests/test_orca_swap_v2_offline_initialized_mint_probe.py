import unittest
from solders.keypair import Keypair
from arb.orca_swap_v2_offline_initialized_mint_probe import initialized_mint_bytes

class OfflineInitializedTokenMintTests(unittest.TestCase):
    def test_mint_layout_and_initialized_flag(self):
        signer=Keypair()
        raw=initialized_mint_bytes(str(signer.pubkey()), 6)
        self.assertEqual(len(raw), 82)
        self.assertEqual(int.from_bytes(raw[:4],"little"),1)
        self.assertEqual(raw[4:36],bytes(signer.pubkey()))
        self.assertEqual(raw[44],6)
        self.assertEqual(raw[45],1)
        self.assertEqual(raw[46:],bytes(36))

    def test_invalid_decimals_rejected(self):
        for invalid in (-1,10,True,"6"):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                initialized_mint_bytes(str(Keypair().pubkey()),invalid)
