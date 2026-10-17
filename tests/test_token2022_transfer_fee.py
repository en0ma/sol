import unittest
from arb.token2022_extensions import transfer_fee_config, fee_for_epoch

def mint_fee_config(older=(5,100,25),newer=(10,50,100)):
    raw=bytearray(166+4+108)
    raw[165]=1
    raw[166:168]=(1).to_bytes(2,"little")
    raw[168:170]=(108).to_bytes(2,"little")
    for start,(epoch,maximum,bps) in ((242,older),(260,newer)):
        raw[start:start+8]=epoch.to_bytes(8,"little")
        raw[start+8:start+16]=maximum.to_bytes(8,"little")
        raw[start+16:start+18]=bps.to_bytes(2,"little")
    return bytes(raw)

class Token2022FeeTests(unittest.TestCase):
    def test_epoch_switch_and_ceiling_fee(self):
        config=transfer_fee_config(mint_fee_config())
        self.assertEqual(config["older"]["basis_points"],25)
        self.assertEqual(config["newer"]["basis_points"],100)
        self.assertEqual(fee_for_epoch(config,9,101)["fee_base_units"],1)
        self.assertEqual(fee_for_epoch(config,10,101)["fee_base_units"],2)
        self.assertEqual(fee_for_epoch(config,10,100000)["fee_base_units"],50)
        self.assertFalse(config["executable_quote"])
        self.assertFalse(config["fee_epoch_authenticated"])

    def test_invalid_config_length_and_basis_points(self):
        raw=bytearray(mint_fee_config())
        raw[168:170]=(107).to_bytes(2,"little")
        with self.assertRaises(ValueError):
            transfer_fee_config(bytes(raw))
        raw=bytearray(mint_fee_config(newer=(10,50,10001)))
        with self.assertRaises(ValueError):
            transfer_fee_config(bytes(raw))

    def test_epoch_not_proven_fails_closed(self):
        config=transfer_fee_config(mint_fee_config())
        with self.assertRaises(ValueError):
            fee_for_epoch(config,4,100)
        with self.assertRaises(ValueError):
            fee_for_epoch(config,10,-1)

    def test_unconfigured_mint_is_no_transfer_fee(self):
        raw=bytes([0])*165+bytes([1])
        self.assertIsNone(transfer_fee_config(raw))
