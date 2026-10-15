import unittest
from arb.cpmm_quote import quote_exact_input,quote_pool
class QuoteTests(unittest.TestCase):
    def test_fee_reduces_output(self):
        no_fee=quote_exact_input(1000000,1000000,10000,0)
        fee=quote_exact_input(1000000,1000000,10000,3000)
        self.assertGreater(no_fee["estimated_output_base_units"],fee["estimated_output_base_units"])
        self.assertEqual(no_fee["estimated_output_base_units"],9900)
    def test_missing_fee_fails_closed(self):
        p={"venue":"raydium_cpmm","verified":True,"address":"p",
           "mints":["a","b"],"vault_base_units":[1000000,1000000]}
        with self.assertRaises(ValueError):
            quote_pool(p,"a",10000)
        self.assertTrue(quote_pool(p,"a",10000,3000)["indicative_only"])
    def test_rejects_bad_types_and_reserves(self):
        for v in (-1,1000000):
            with self.assertRaises(ValueError):quote_exact_input(1000,1000,10,v)
        with self.assertRaises(TypeError):quote_exact_input(1000.0,1000,10,3000)
