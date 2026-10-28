import base64,unittest
from unittest.mock import patch
from types import SimpleNamespace
from arb.meteora_damm_v2_native_quote import quote_pool_account
from arb.meteora_damm_v2 import PROGRAM

class OfficialSDKOnlyTests(unittest.TestCase):
 def test_quote_uses_official_sdk_and_authenticated_pool(self):
  account={"owner":PROGRAM,"executable":False,
           "data":[base64.b64encode(b"pool").decode(),"base64"]}
  with patch("arb.meteora_damm_v2_native_quote.decode",return_value={
      "token_a_mint":"A","token_b_mint":"B"}),patch(
      "arb.meteora_damm_v2_native_quote.subprocess.run",
      return_value=SimpleNamespace(returncode=0,stdout='{"amount_out":124}',stderr="")) as run:
   result=quote_pool_account(account,mint_in="A",amount_in=1000,
      fork_unix_timestamp=42,fork_clock_slot=70)
   self.assertEqual(result["amount_out"],124)
   self.assertEqual(result["native_pricing_engine"],"OFFICIAL_METEORA_RUST_SDK")
   self.assertTrue(run.called)
 def test_unauthenticated_pool_is_rejected(self):
  with self.assertRaises(ValueError):
   quote_pool_account({"owner":"wrong","executable":False},mint_in="A",
      amount_in=100,fork_unix_timestamp=42,fork_clock_slot=70)
if __name__=="__main__":unittest.main()
