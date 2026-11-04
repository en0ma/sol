import unittest,hashlib
from arb.cpmm_config import decode_amm_config,DISC,CONFIG_SIZE
class ConfigTests(unittest.TestCase):
    def fixture(self,trade=2500,creator=100):
        x=bytearray(CONFIG_SIZE);x[:8]=DISC
        x[12:20]=trade.to_bytes(8,"little")
        x[108:116]=creator.to_bytes(8,"little")
        return bytes(x)
    def test_decodes_trade_and_creator(self):
        x=decode_amm_config(self.fixture())
        self.assertEqual(x["trade_fee_rate_ppm"],2500)
        self.assertEqual(x["creator_fee_rate_ppm"],100)
    def test_invalid_data_fails_closed(self):
        with self.assertRaises(ValueError):decode_amm_config(bytes(CONFIG_SIZE))
        with self.assertRaises(ValueError):decode_amm_config(self.fixture(999900,200))
