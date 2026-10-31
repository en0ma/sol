import unittest
from unittest.mock import patch
from arb.fixture_aux_fee_decoder import decode_native_config_fee
from arb.raydium_cpmm import PROGRAM as CPMM_PROGRAM

class ConfigFeeTests(unittest.TestCase):
    def fixture(self):
        return {"state_account_addresses":["cfg"],"accounts":{
            "cfg":{"owner":CPMM_PROGRAM,"executable":False,"data":["AQ==","base64"]}}}
    def test_cpmm_bad_fee_range_is_rejected(self):
        for value in (-1,1_000_000,True):
            with self.subTest(value=value),patch("arb.fixture_aux_fee_decoder.decode_amm_config",
                     return_value={"trade_fee_rate_ppm":value,"creator_fee_rate_ppm":0}):
                with self.assertRaisesRegex(ValueError,"fee ppm invalid"):
                    decode_native_config_fee("raydium_cpmm",{"amm_config":"cfg"},self.fixture())
    def test_cpmm_bad_creator_fee_range_rejected(self):
        with patch("arb.fixture_aux_fee_decoder.decode_amm_config",
                   return_value={"trade_fee_rate_ppm":2500,"creator_fee_rate_ppm":1_000_000}):
            with self.assertRaises(ValueError):
                decode_native_config_fee("raydium_cpmm",{"amm_config":"cfg"},self.fixture())
    def test_duplicate_config_source_rejected(self):
        fixture=self.fixture()
        fixture["state_account_addresses"].append("cfg")
        with self.assertRaisesRegex(ValueError,"duplicate"):
            decode_native_config_fee("raydium_cpmm",{"amm_config":"cfg"},fixture)
    def test_no_ambiguous_config_address(self):
        with self.assertRaisesRegex(ValueError,"invalid pool-referenced"):
            decode_native_config_fee("raydium_cpmm",{"amm_config":None},self.fixture())
if __name__=="__main__":unittest.main()
