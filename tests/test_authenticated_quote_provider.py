import unittest
from arb.authenticated_quote_provider import from_snapshot
S={"venue":"raydium_cpmm","address":"pool-1","mints":["A","B"],
   "slot":500,"observed_unix":1000,"source_authenticated":True,
   "verified":True,"account_owner_verified":True,
   "snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
   "trade_fee_authenticated":True,"trade_fee_ppm":2500,
   "vault_base_units":[100000,200000]}
class Tests(unittest.TestCase):
 def test_bidirectional_real_integer_quote_math(self):
    quote,registry=from_snapshot([S],now=1001)
    a=quote({"venue":"raydium_cpmm","pool":"pool-1","input_mint":"A","output_mint":"B"},1000)
    b=quote({"venue":"raydium_cpmm","pool":"pool-1","input_mint":"B","output_mint":"A"},1000)
    self.assertEqual(a["amount_out"],1975)
    self.assertNotEqual(a["amount_out"],b["amount_out"])
    self.assertEqual(registry["pool_count"],1)
    self.assertFalse(a.get("simulation_verified",False))
 def test_reject_unverified_fee(self):
    quote,_=from_snapshot([dict(S,trade_fee_authenticated=False)],now=1001)
    with self.assertRaisesRegex(ValueError,"fee not authenticated"):
        quote({"venue":"raydium_cpmm","pool":"pool-1","input_mint":"A","output_mint":"B"},1000)
 def test_reject_other_venue_without_invented_model(self):
    s=dict(S,venue="meteora_dlmm")
    quote,_=from_snapshot([s],now=1001)
    with self.assertRaisesRegex(ValueError,"not integrated"):
        quote({"venue":"meteora_dlmm","pool":"pool-1","input_mint":"A","output_mint":"B"},1000)
 def test_reject_stale_snapshot(self):
    quote,registry=from_snapshot([dict(S,observed_unix=800)],now=1001)
    self.assertEqual(registry["pool_count"],0)
    with self.assertRaisesRegex(ValueError,"not in authenticated snapshot"):
        quote({"venue":"raydium_cpmm","pool":"pool-1","input_mint":"A","output_mint":"B"},1000)
 def test_reject_reserve_and_wrong_direction(self):
    quote,_=from_snapshot([S],now=1001)
    with self.assertRaisesRegex(ValueError,"direction"):
        quote({"venue":"raydium_cpmm","pool":"pool-1","input_mint":"C","output_mint":"B"},1000)
    quote,_=from_snapshot([dict(S,vault_base_units=[0,200])],now=1001)
    with self.assertRaisesRegex(ValueError,"reserve"):
        quote({"venue":"raydium_cpmm","pool":"pool-1","input_mint":"A","output_mint":"B"},1000)
if __name__=="__main__":unittest.main()
