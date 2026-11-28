import unittest
from arb.cpmm_quote import quote_native_fee_candidates,quote_source_exact_input
from arb.token_vaults import TOKEN_PROGRAM
class Tests(unittest.TestCase):
 def test_fractional_and_integer_candidates_distinct_on_dust(self):
  found=False
  for n in range(1,100):
   try:q=quote_native_fee_candidates(1000,10000,n,2500)
   except ValueError:continue
   self.assertLessEqual(q["ceil_fee_then_swap_output_base_units"],q["floor_fee_then_swap_output_base_units"])
   if q["fractional_invariant_output_base_units"] != q["floor_fee_then_swap_output_base_units"]:found=True
  self.assertTrue(found)
 def test_reject_invalid(self):
  with self.assertRaises(ValueError):
   quote_native_fee_candidates(0,1000,10,2500)
class RaydiumOfficialCurvePortTests(unittest.TestCase):
 def state(self,mode=0,enabled=True):
  return {"swap_enabled":True,"open_time":1,"token_0_program":TOKEN_PROGRAM,
   "token_1_program":TOKEN_PROGRAM,"creator_fee_on":mode,
   "enable_creator_fee":enabled,
   **{f"{kind}_fees_token_{side}":0 for kind in ("protocol","fund","creator") for side in (0,1)}}
 def config(self,trade=3000,creator=2000):
  return {"fee_verified_onchain":True,"trade_fee_rate_ppm":trade,
   "creator_fee_rate_ppm":creator,"protocol_fee_rate_ppm":100000,
   "fund_fee_rate_ppm":50000}
 def test_raydium_creator_fee_direction_and_aggregate_ceil(self):
  for mode,first,second in ((0,True,True),(1,True,False),(2,False,True)):
   with self.subTest(mode=mode):
    for input_zero,expected in ((True,first),(False,second)):
     q=quote_source_exact_input(self.state(mode),self.config(),
       reserve_0=1000000,reserve_1=2000000,amount_in=10007,
       input_is_token_0=input_zero,observed_unix=50)
     self.assertEqual(q["creator_fee_on_input"],expected)
     self.assertFalse(q["protocol_exact_verified"])
     self.assertGreater(q["amount_out"],0)
 def test_excludes_accrued_fees_and_pool_not_open(self):
  state=self.state()
  state["protocol_fees_token_0"]=200000
  quote=quote_source_exact_input(state,self.config(),reserve_0=1000000,
   reserve_1=2000000,amount_in=10000,input_is_token_0=True,observed_unix=20)
  self.assertEqual(quote["effective_reserves"],[800000,2000000])
  state["open_time"]=30
  with self.assertRaisesRegex(ValueError,"not yet opened"):
   quote_source_exact_input(state,self.config(),reserve_0=1000000,
    reserve_1=2000000,amount_in=10000,input_is_token_0=True,observed_unix=20)
 def test_fee_rounding_known_reference(self):
  q=quote_source_exact_input(self.state(0),self.config(trade=2500,creator=1000),
   reserve_0=1000000,reserve_1=2000000,amount_in=10001,
   input_is_token_0=True,observed_unix=50)
  self.assertEqual(q["trade_fee"]+q["creator_fee"],36)
  self.assertEqual(q["creator_fee"],10)
  self.assertEqual(q["amount_out"],(10001-36)*2000000//(1000000+10001-36))
 def test_rejects_unverified_fee_config(self):
  with self.assertRaisesRegex(ValueError,"authentication"):
   quote_source_exact_input(self.state(),{"trade_fee_rate_ppm":3000},
    reserve_0=1000000,reserve_1=2000000,amount_in=10000,
    input_is_token_0=True,observed_unix=20)
if __name__=="__main__":unittest.main()
