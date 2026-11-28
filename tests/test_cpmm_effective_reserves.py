import unittest
from arb.cpmm_creator_fee_quote import effective_reserves,calculate
class Tests(unittest.TestCase):
 def test_accrued_fee_liabilities_change_price(self):
  state={}
  for index,values in ((0,(4,5,6)),(1,(7,8,9))):
   for key,value in zip(("protocol_fees","fund_fees","creator_fees"),values):
    state[f"{key}_token_{index}"]=value
  net=effective_reserves(state,[1000,2000])
  self.assertEqual(net,[985,1976])
  raw=calculate(1000,2000,100,2500,1000,0,0)
  corrected=calculate(*net,100,2500,1000,0,0)
  self.assertEqual(net,[985,1976])
  self.assertGreater(raw["estimated_output_base_units"],0)
  self.assertGreater(corrected["estimated_output_base_units"],0)
  self.assertNotEqual((1000,2000),tuple(net))
 def test_unproven_liabilities_fail_closed(self):
  with self.assertRaises(ValueError):effective_reserves({},[1000,2000])
  state={f"{key}_token_{i}":1000 for i in (0,1)
    for key in ("protocol_fees","fund_fees","creator_fees")}
  with self.assertRaises(ValueError):effective_reserves(state,[1000,2000])
if __name__=="__main__":unittest.main()
