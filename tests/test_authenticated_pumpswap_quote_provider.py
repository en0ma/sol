import unittest
from arb.authenticated_quote_provider import from_snapshot
S={"venue":"pumpswap","address":"pump-pool","mints":["BASE","QUOTE"],
"base_mint":"BASE","quote_mint":"QUOTE","base_reserve":100000,
"quote_vault_balance":200000,"virtual_quote_reserves":5000,
"protocol_fees_accrued":1000,"creator_fees_accrued":500,
"trade_fee_authenticated":True,"fee_verified_onchain":True,
"effective_fee_verified":True,"trade_fee_ppm":2500,
"global_config":{"effective_fee_verified":True,"sell_enabled":True,"buy_enabled":True},
"slot":500,"observed_unix":1000,"verified":True,"source_authenticated":True,
"account_owner_verified":True,"snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL"}
class PumpQuoteTests(unittest.TestCase):
 def test_bidirectional_authenticated_quotes(self):
    q,_=from_snapshot([S],now=1001)
    for src,dst in (("BASE","QUOTE"),("QUOTE","BASE")):
      r=q({"venue":"pumpswap","pool":"pump-pool","input_mint":src,"output_mint":dst},1000)
      self.assertGreater(r["amount_out"],0)
      self.assertFalse(r.get("simulation_verified",False))
      self.assertEqual(r["snapshot_slot"],500)
 def test_reject_missing_dynamic_fee(self):
    q,_=from_snapshot([dict(S,effective_fee_verified=False)],now=1001)
    with self.assertRaisesRegex(ValueError,"effective fee"):
      q({"venue":"pumpswap","pool":"pump-pool","input_mint":"BASE","output_mint":"QUOTE"},1000)
 def test_reject_direction_disabled(self):
    q,_=from_snapshot([dict(S,global_config=dict(S["global_config"],sell_enabled=False))],now=1001)
    with self.assertRaisesRegex(ValueError,"direction disabled"):
      q({"venue":"pumpswap","pool":"pump-pool","input_mint":"BASE","output_mint":"QUOTE"},1000)
 def test_unspendable_fee_vault_fails(self):
    q,_=from_snapshot([dict(S,protocol_fees_accrued=200000)],now=1001)
    with self.assertRaises(ValueError):
      q({"venue":"pumpswap","pool":"pump-pool","input_mint":"BASE","output_mint":"QUOTE"},1000)
 def test_stale_snapshot_unavailable(self):
    q,r=from_snapshot([dict(S,observed_unix=10)],now=1001)
    self.assertEqual(r["pool_count"],0)
    with self.assertRaisesRegex(ValueError,"not in authenticated snapshot"):
      q({"venue":"pumpswap","pool":"pump-pool","input_mint":"BASE","output_mint":"QUOTE"},1000)
if __name__=="__main__":unittest.main()
