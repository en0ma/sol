import unittest
from arb.meteora_dlmm_source_fee_decoder import (
    static_parameters,variable_parameters,source_fee_bounds,
    FEE_PRECISION,MAX_FEE_NUMERATOR
)
from arb.meteora_dlmm import SIZE,DISC

class NativeDlmmFeeSourceTests(unittest.TestCase):
    def pool(self):
        b=bytearray(SIZE)
        b[:8]=DISC
        b[8:10]=(20).to_bytes(2,"little")
        b[10:12]=(10).to_bytes(2,"little")
        b[12:14]=(30).to_bytes(2,"little")
        b[14:16]=(5000).to_bytes(2,"little")
        b[16:20]=(100).to_bytes(4,"little")
        b[20:24]=(5000).to_bytes(4,"little")
        b[24:28]=(-440000).to_bytes(4,"little",signed=True)
        b[28:32]=(440000).to_bytes(4,"little",signed=True)
        b[32:34]=(1000).to_bytes(2,"little")
        b[34]=0
        b[40:44]=(20).to_bytes(4,"little")
        b[44:48]=(10).to_bytes(4,"little")
        b[48:52]=(5).to_bytes(4,"little",signed=True)
        b[56:64]=(123456789).to_bytes(8,"little",signed=True)
        return b
    def test_borsh_static_and_variable_fee_fields_and_bounds(self):
        raw=bytes(self.pool())
        s=static_parameters(raw)
        v=variable_parameters(raw)
        self.assertEqual(s["base_factor"],20)
        self.assertEqual(s["min_bin_id"],-440000)
        self.assertEqual(s["max_bin_id"],440000)
        self.assertEqual(v["volatility_accumulator"],20)
        self.assertEqual(v["index_reference"],5)
        self.assertEqual(v["last_update_timestamp"],123456789)
        result=source_fee_bounds(raw,bin_step=25,observed_unix=123456800)
        self.assertEqual(result["base_fee_rate_numerator"],5000)
        self.assertEqual(result["fee_precision"],FEE_PRECISION)
        self.assertEqual(result["maximum_total_fee_rate_numerator"],MAX_FEE_NUMERATOR)
        self.assertFalse(result["dynamic_fee_verified"])
        self.assertFalse(result["protocol_exact_verified"])
        self.assertFalse(result["broadcast"])
    def test_rejects_volatility_exceeding_configured_cap(self):
        raw=self.pool()
        raw[40:44]=(6000).to_bytes(4,"little")
        with self.assertRaisesRegex(ValueError,"volatility"):
            source_fee_bounds(bytes(raw),bin_step=25,observed_unix=1)
    def test_rejects_invalid_bin_step_and_untrusted_layout(self):
        raw=bytes(self.pool())
        with self.assertRaisesRegex(ValueError,"bin step"):
            source_fee_bounds(raw,bin_step=0,observed_unix=1)
        with self.assertRaises(ValueError):
            static_parameters(raw[:-1])
        with self.assertRaises(ValueError):
            static_parameters(b"X"*SIZE)
    def test_rejects_invalid_static_fee_overshoot(self):
        raw=self.pool()
        raw[34]=7
        with self.assertRaisesRegex(ValueError,"ceiling"):
            source_fee_bounds(bytes(raw),bin_step=25,observed_unix=1)

if __name__=="__main__":unittest.main()
