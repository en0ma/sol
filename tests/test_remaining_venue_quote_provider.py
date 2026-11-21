import unittest
from arb.authenticated_quote_provider import from_snapshot
Q=1<<64
COMMON={"address":"p","mints":["A","B"],"slot":500,"observed_unix":1000,
"verified":True,"source_authenticated":True,"account_owner_verified":True,
"snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
"trade_fee_authenticated":True,"trade_fee_ppm":2500}
DLMM=dict(COMMON,venue="meteora_dlmm",token_x_mint="A",token_y_mint="B",
active_bin_authenticated=True,bin_liquidity_authenticated=True,
active_bin_price_q64=Q,active_bin_x_reserve=100000,active_bin_y_reserve=100000,
max_within_segment_input_by_mint={"A":1000,"B":1000})
DAMM=dict(COMMON,venue="meteora_damm_v2",token_a_mint="A",token_b_mint="B",
dynamic_fee_authenticated=True,price_segment_authenticated=True,
sqrt_price_x64=Q,liquidity=1000000,
next_segment_sqrt_by_input_mint={"A":Q-Q//10,"B":Q+Q//10},
max_within_segment_input_by_mint={"A":1000,"B":1000})
AMM=dict(COMMON,venue="raydium_amm_v4",base_mint="A",quote_mint="B",
market_accounts_authenticated=True,effective_reserves_authenticated=True,
effective_reserves_base_units=[100000,200000])
class TestRemainingModels(unittest.TestCase):
 def runquote(self,s,m="A",n=100):
    q,_=from_snapshot([s],now=1001)
    return q({"venue":s["venue"],"pool":"p","input_mint":m,
              "output_mint":"B" if m=="A" else "A"},n)
 def test_three_venues_two_directions(self):
    for state in (DLMM,DAMM,AMM):
      for mint in ("A","B"):
        with self.subTest(venue=state["venue"],mint=mint):
          result=self.runquote(state,mint)
          self.assertGreater(result["amount_out"],0)
          self.assertFalse(result["protocol_exact_quote_verified"])
 def test_authentication_gates(self):
    for state,key in ((DLMM,"active_bin_authenticated"),(DAMM,"dynamic_fee_authenticated"),(AMM,"effective_reserves_authenticated")):
      with self.assertRaises(ValueError):self.runquote(dict(state,**{key:False}))
 def test_segment_crossing(self):
    for state in (DLMM,DAMM):
      with self.assertRaises(ValueError):self.runquote(state,n=1001)
 def test_fee_rejection(self):
    for state in (DLMM,DAMM,AMM):
      with self.assertRaises(ValueError):self.runquote(dict(state,trade_fee_authenticated=False))
 def test_net_reserve_validation(self):
    with self.assertRaises(ValueError):self.runquote(dict(AMM,effective_reserves_base_units=None))
if __name__=="__main__":unittest.main()
