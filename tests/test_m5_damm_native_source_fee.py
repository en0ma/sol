import unittest
from arb.meteora_damm_v2_source_fee_decoder import decode_fee_state,effective_base_fee_from_pool
from arb.meteora_damm_v2 import SIZE,DISC
from unittest.mock import patch
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
class DAMMSourcePoolFeeDecoderTests(unittest.TestCase):
    def pool(self,*,dynamic=False,fee_mode=1,clock=100):
        raw=bytearray(SIZE)
        raw[:8]=DISC
        raw[8:16]=(10000000).to_bytes(8,"little")
        raw[16]=0
        raw[22:24]=(3).to_bytes(2,"little")
        raw[24:32]=(10).to_bytes(8,"little")
        raw[32:40]=(1000000).to_bytes(8,"little")
        raw[48:51]=bytes((20,10,5))
        raw[56]=1 if dynamic else 0
        raw[64:68]=(4000).to_bytes(4,"little")
        raw[68:72]=(10).to_bytes(4,"little")
        raw[72:74]=(25).to_bytes(2,"little")
        raw[74:76]=(5).to_bytes(2,"little")
        raw[76:78]=(15).to_bytes(2,"little")
        raw[78:80]=(5000).to_bytes(2,"little")
        raw[80:88]=(10).to_bytes(8,"little")
        raw[472:480]=clock.to_bytes(8,"little")
        raw[480]=1
        raw[481]=0
        raw[484]=fee_mode
        raw[485]=1
        return bytes(raw)
    def test_actual_pool_fee_struct_byte_offsets(self):
        value=decode_fee_state(self.pool(dynamic=True,fee_mode=2))
        self.assertEqual(value["base_fee"]["cliff_fee_numerator"],10000000)
        self.assertEqual(value["base_fee"]["period_frequency"],10)
        self.assertEqual(value["dynamic_fee"]["bin_step"],25)
        self.assertEqual(value["dynamic_fee"]["volatility_reference"],0)
        self.assertEqual(value["native_collection_mode"],"QUOTE_COMPOUNDING")
        self.assertTrue(value["fee_source_layout_verified"])
    @patch("arb.meteora_damm_v2_source_fee_decoder.decode")
    def test_source_timestamp_scheduler_amount(self,decode):
        decode.return_value={"pool_status":0}
        result=effective_base_fee_from_pool(self.pool(),source_slot=999,
                observed_unix=125)
        self.assertEqual(result["activation_clock"],"observed_unix")
        self.assertEqual(result["base_fee_periods_elapsed"],2)
        self.assertEqual(result["base_fee_numerator"],8000000)
        self.assertFalse(result["protocol_exact_total_fee_verified"])
    def test_unrecognized_collection_mode_rejected(self):
        raw=bytearray(self.pool());raw[484]=7
        with self.assertRaisesRegex(ValueError,"mode"):
            decode_fee_state(bytes(raw))
    def test_bad_dynamic_fee_config_rejected(self):
        raw=bytearray(self.pool(dynamic=True))
        raw[72:74]=b"\x00\x00"
        with self.assertRaisesRegex(ValueError,"dynamic"):
            decode_fee_state(bytes(raw))
    def test_wrong_pool_length_rejected(self):
        with self.assertRaisesRegex(ValueError,"bytes"):
            decode_fee_state(self.pool()[:-1])
if __name__=="__main__":unittest.main()
