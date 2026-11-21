"""Original DBC Q64 fee scheduler real source vectors, independent of SDK."""
import unittest
from arb.meteora_dbc_native_fee import fee_numerator,price_with_fee,fee_ceiling


def config():
    raw=bytearray(1048)
    raw[104:112]=(990_000_000).to_bytes(8,"little")
    raw[112:120]=(1).to_bytes(8,"little")
    raw[120:128]=(4416).to_bytes(8,"little")
    raw[128:130]=(6).to_bytes(2,"little")
    raw[130]=1  # exponential
    raw[136]=0  # dynamic fee disabled
    raw[232]=0  # fees collected in quote token
    return bytes(raw)


class DbcNativeFeeTests(unittest.TestCase):
    def test_original_mainnet_exponential_fee_numerator(self):
        self.assertEqual(fee_numerator(config(),current_point=1793287181,
                                     activation_point=1793286996),30012878)

    def test_original_real_quote_fee_rounded_input(self):
        got=price_with_fee(config(),direction="quote_to_base",amount_in=10000,
            current_point=1793287181,activation_point=1793286996,
            price_curve_fn=lambda a:{
                "output_amount":389101089,"next_sqrt_price":92098393836828734}
                if a==9699 else self.fail("fee-excluded input mismatch"))
        self.assertEqual(got["actual_input_amount"],9699)
        self.assertEqual(got["protocol_fee"],60)
        self.assertEqual(got["trading_fee"],241)
        self.assertEqual(got["output_amount"],389101089)

    def test_original_real_quote_output_fee(self):
        got=price_with_fee(config(),direction="base_to_quote",amount_in=997886654,
            current_point=1793287181,activation_point=1793286996,
            price_curve_fn=lambda a:{
                "output_amount":24873,"next_sqrt_price":92098276515258379}
                if a==997886654 else self.fail("wrong input"))
        self.assertEqual(got["output_amount"],24126)
        self.assertEqual(got["protocol_fee"],149)
        self.assertEqual(got["trading_fee"],598)

    def test_dynamic_fee_rejected(self):
        b=bytearray(config());b[136]=1
        with self.assertRaisesRegex(ValueError,"variable fee"):
            fee_numerator(bytes(b),current_point=1793287181,
                          activation_point=1793286996)

    def test_nonzero_fee_cannot_be_negative_or_overflow(self):
        with self.assertRaisesRegex(ValueError,"unsupported"):
            fee_ceiling(10,1_000_000_000)


if __name__=="__main__":unittest.main()
