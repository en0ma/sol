import unittest
from arb.venue_quote_adapter import quote
class Tests(unittest.TestCase):
 def test_seven_venue_fail_closed_without_source_evidence(self):
  for v in ("orca","raydium_clmm","meteora_dlmm","meteora_damm_v2",
            "pumpswap","raydium_cpmm","raydium_amm_v4"):
   with self.subTest(v=v),self.assertRaises(ValueError):
    quote(v,{},"mint",100,evidence={"source_authenticated":False})
 def test_tick_venues_require_authenticated_boundaries(self):
  for v in ("orca","raydium_clmm"):
   with self.assertRaises((ValueError,KeyError)):
    quote(v,{},"mint",100,evidence={"source_authenticated":True})
 def test_dynamic_fee_venues_no_defaults(self):
  for v in ("meteora_dlmm","meteora_damm_v2","pumpswap"):
   with self.assertRaises(ValueError):
    quote(v,{},"mint",100,evidence={"source_authenticated":True})
if __name__=="__main__":unittest.main()
