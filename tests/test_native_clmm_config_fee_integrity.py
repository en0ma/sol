import unittest
from unittest.mock import patch
from arb.fixture_aux_fee_decoder import decode_native_config_fee
from arb.raydium_clmm import PROGRAM
from arb.raydium_clmm_fee_snapshot import DISC

class NativeCLMMFeeTests(unittest.TestCase):
    def fixture(self,spacing=16,fee=2500):
        data=bytearray(53)
        data[:8]=DISC
        data[47:51]=fee.to_bytes(4,"little")
        data[51:53]=spacing.to_bytes(2,"little")
        import base64
        return {"state_account_addresses":["cfg"],"accounts":{
            "cfg":{"owner":PROGRAM,"executable":False,"data":[base64.b64encode(data).decode(),"base64"]}}}
    def test_native_clmm_fee_and_pool_spacing_bound(self):
        result=decode_native_config_fee("raydium_clmm",{"amm_config":"cfg","tick_spacing":16},self.fixture())
        self.assertEqual(result["effective_quote_fee_ppm"],2500)
        self.assertTrue(result["trade_fee_authenticated"])
        self.assertFalse(result["broadcast"])
    def test_wrong_pool_spacing_rejected(self):
        for spacing in (0,8,True):
            with self.subTest(spacing=spacing):
                with self.assertRaises(ValueError):
                    decode_native_config_fee("raydium_clmm",{"amm_config":"cfg","tick_spacing":spacing},self.fixture())
    def test_oversized_native_fee_rejected(self):
        with self.assertRaises(ValueError):
            decode_native_config_fee("raydium_clmm",{"amm_config":"cfg","tick_spacing":16},self.fixture(fee=1_000_000))
    def test_wrong_owner_rejected(self):
        captured=self.fixture()
        captured["accounts"]["cfg"]["owner"]="incorrect"
        with self.assertRaisesRegex(ValueError,"owner not authenticated"):
            decode_native_config_fee("raydium_clmm",{"amm_config":"cfg","tick_spacing":16},captured)
if __name__=="__main__":unittest.main()
