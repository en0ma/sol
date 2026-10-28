import unittest
from arb.meteora_damm_v2_native_quote import quote_pool_account
class SDKQuoteFailClosedTests(unittest.TestCase):
 def test_rejects_partial_python_reserve_fee_model(self):
  with self.assertRaisesRegex(ValueError,"authenticated Meteora"):
   quote_pool_account({"vault_base_units":[10000,20000],
                       "effective_fee_ppm":3000},
                       mint_in="A",amount_in=100,
                       fork_unix_timestamp=10,fork_clock_slot=20)
 def test_rejects_missing_clock(self):
  from unittest.mock import patch
  from arb.meteora_damm_v2 import PROGRAM
  import base64
  pool={"owner":PROGRAM,"executable":False,
        "data":[base64.b64encode(b"fake").decode(),"base64"]}
  with patch("arb.meteora_damm_v2_native_quote.decode",
             return_value={"token_a_mint":"A","token_b_mint":"B"}):
   with self.assertRaisesRegex(ValueError,"Clock"):
    quote_pool_account(pool,mint_in="A",amount_in=100,
                       fork_unix_timestamp=0,fork_clock_slot=20)
if __name__=="__main__":unittest.main()
