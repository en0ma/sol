import base64,unittest
from unittest.mock import patch
from arb.fixture_all_venue_signed_quotes import quote_leg
from arb.orca_tick_math import sqrt_price_from_tick_index
from arb.whirlpool_ticks import FIXED_LEN,DISC
from arb.orca_whirlpool import PROGRAM
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
class SourceOrcaArrayTests(unittest.TestCase):
 def fixture(self):
  raw=bytearray(FIXED_LEN)
  raw[:8]=DISC
  return {"state_accounts_observed_slot":77,"state_account_addresses":["tick-pda"],
    "accounts":{"tick-pda":{"owner":PROGRAM,"executable":False,
        "data":[base64.b64encode(raw).decode(),"base64"]}},
    "route_mints":["A","B","C"],**SAFE}
 def rows(self):
  return [{"venue":"orca","address":"POOL","mints":["A","B"],
     "snapshot_slot":77,"decoded_pool_state":{
       "token_mint_a":"A","token_mint_b":"B","tick_spacing":10,
       "tick_current_index":5,"sqrt_price_x64":sqrt_price_from_tick_index(5),
       "liquidity":10**9,"fee_rate_hundredths_bps":1000}},
       {"venue":"raydium_cpmm","address":"OTHER","mints":["B","C"],"snapshot_slot":77}]
 @patch("arb.orca_whirlpool.b58",return_value="POOL")
 @patch("arb.orca_multitick_quote.quote_from_decoded_arrays")
 @patch("arb.whirlpool_ticks.decode_fixed_ticks")
 @patch("arb.whirlpool_ticks.addresses")
 @patch("arb.fixture_all_venue_signed_quotes.extract_pool_states")
 def test_canonical_source_array_binds_existing_multitick(self,rows,addresses,decode,quote,parent):
  rows.return_value=self.rows()
  addresses.return_value=["tick-pda"]
  decode.return_value=[{"tick_index":0,"liquidity_net":"-100","liquidity_gross":"100"}]
  quote.return_value={"estimated_output_base_units":666,"ticks_crossed":1}
  result=quote_leg(self.fixture(),leg_index=0,amount_in=1000,observed_unix=1)
  self.assertEqual(result["quote_status"],"SOURCE_BOUND_INDICATIVE")
  self.assertEqual(result["predicted_output_base_units"],666)
  self.assertEqual(quote.call_args.args[3][0]["start_tick"],0)
  self.assertFalse(result["protocol_exact_verified"])
 @patch("arb.orca_whirlpool.b58",return_value="POOL")
 @patch("arb.whirlpool_ticks.addresses")
 @patch("arb.fixture_all_venue_signed_quotes.extract_pool_states")
 def test_forged_tick_pda_never_becomes_native_quote(self,rows,addresses,parent):
  rows.return_value=self.rows()
  addresses.return_value=["different-pda"]
  result=quote_leg(self.fixture(),leg_index=0,amount_in=1000,observed_unix=1)
  self.assertEqual(result["quote_status"],"NATIVE_QUOTE_BLOCKED")
  self.assertIn("PDA mismatch",result["reason"])
  self.assertFalse(result["broadcast"])
 @patch("arb.orca_whirlpool.b58",return_value="OTHER")
 @patch("arb.whirlpool_ticks.addresses")
 @patch("arb.fixture_all_venue_signed_quotes.extract_pool_states")
 def test_other_whirlpool_tick_account_is_ignored(self,rows,addresses,parent):
  rows.return_value=self.rows()
  addresses.return_value=["tick-pda"]
  result=quote_leg(self.fixture(),leg_index=0,amount_in=1000,observed_unix=1)
  self.assertEqual(result["quote_status"],"SOURCE_BOUND_INDICATIVE")
  self.assertFalse(result["broadcast"])
 @patch("arb.orca_whirlpool.b58",return_value="POOL")
 @patch("arb.orca_multitick_quote.quote_from_decoded_arrays")
 @patch("arb.whirlpool_ticks.decode_dynamic_ticks")
 @patch("arb.whirlpool_ticks.addresses")
 @patch("arb.fixture_all_venue_signed_quotes.extract_pool_states")
 def test_dynamic_source_whirlpool_tick_array_is_routed(self,rows,addresses,decode,quote,parent):
  from arb.whirlpool_ticks import DYNAMIC_DISC,DYNAMIC_MIN_LEN
  rows.return_value=self.rows()
  addresses.return_value=["tick-pda"]
  fixture=self.fixture()
  raw=bytearray(DYNAMIC_MIN_LEN)
  raw[:8]=DYNAMIC_DISC
  fixture["accounts"]["tick-pda"]["data"]=[base64.b64encode(raw).decode(),"base64"]
  decode.return_value=[]
  quote.return_value={"estimated_output_base_units":800}
  result=quote_leg(fixture,leg_index=0,amount_in=1000,observed_unix=1)
  self.assertEqual(result["predicted_output_base_units"],800)
  self.assertEqual(quote.call_args.args[3][0]["status"],"DYNAMIC_VALID")
if __name__=="__main__":unittest.main()
