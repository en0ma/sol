import unittest
from unittest.mock import patch
from arb.meteora_dlmm_source_fee_envelope import quote_fee_envelope
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
POOL="source-dlmm-pool"
class DlmmSourceEnvelopeTests(unittest.TestCase):
    def fixture(self):
        return {"state_accounts_observed_slot":123,**SAFE}
    def rows(self):
        return [{"venue":"meteora_dlmm","address":POOL,
                 "decoded_pool_state":{"token_x_mint":"X",
                     "token_y_mint":"Y","active_id":5}}]
    @patch("arb.meteora_dlmm_source_fee_envelope.quote_bins")
    @patch("arb.meteora_dlmm_source_fee_envelope.fee_bounds_from_fixture")
    @patch("arb.meteora_dlmm_source_fee_envelope.directional_bins")
    @patch("arb.meteora_dlmm_source_fee_envelope.decode_from_fixture")
    @patch("arb.meteora_dlmm_source_fee_envelope.extract_pool_states")
    def test_real_source_fee_endpoints_price_same_amount_without_claiming_exactness(
            self,rows,decode,walk,rates,quote):
        rows.return_value=self.rows()
        decode.return_value={"array_index":0,"bin_count":70}
        walk.return_value={"bins":[{"bin_id":5,"amount_x":200,"amount_y":200,
                                    "price_q64":1<<64}]}
        rates.return_value={"minimum_total_fee_rate_numerator":1000,
                             "maximum_total_fee_rate_numerator":100000000}
        quote.side_effect=[
            {"amount_out":100,"fee_input_base_units":1,"bins_traversed":[]},
            {"amount_out":90,"fee_input_base_units":10,"bins_traversed":[]}]
        result=quote_fee_envelope(self.fixture(),pool=POOL,mint_in="X",
            amount_in=101,observed_unix=123,maximum_arrays=1)
        self.assertEqual(result["lower_output_bound"],90)
        self.assertEqual(result["upper_output_bound"],100)
        self.assertFalse(result["effective_fee_verified"])
        self.assertFalse(result["protocol_exact_verified"])
        self.assertEqual(quote.call_count,2)
        self.assertFalse(result["broadcast"])
    @patch("arb.meteora_dlmm_source_fee_envelope.decode_from_fixture")
    @patch("arb.meteora_dlmm_source_fee_envelope.extract_pool_states")
    def test_missing_real_active_bin_produces_explicit_blocker(self,rows,decode):
        rows.return_value=self.rows()
        decode.side_effect=ValueError("bin array missing")
        result=quote_fee_envelope(self.fixture(),pool=POOL,mint_in="Y",
            amount_in=101,observed_unix=123,maximum_arrays=1)
        self.assertEqual(result["status"],"SOURCE_NATIVE_DLMM_BIN_ARRAY_BLOCKED")
        self.assertNotIn("lower_output_bound",result)
    @patch("arb.meteora_dlmm_source_fee_envelope.extract_pool_states")
    def test_wrong_mint_is_rejected(self,rows):
        rows.return_value=self.rows()
        with self.assertRaisesRegex(ValueError,"input mint"):
            quote_fee_envelope(self.fixture(),pool=POOL,mint_in="Z",amount_in=100,
                observed_unix=123)
if __name__=="__main__":unittest.main()
