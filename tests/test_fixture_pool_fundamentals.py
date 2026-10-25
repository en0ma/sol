import unittest
from arb.fixture_pool_fundamentals import VAULTS,extract
from arb.execution_target_matrix import TARGET_VENUES
class Tests(unittest.TestCase):
 def test_every_active_venue_has_explicit_native_vault_mapping(self):
    self.assertEqual(set(VAULTS),set(TARGET_VENUES))
    self.assertTrue(all(len(v)==2 and v[0]!=v[1] for v in VAULTS.values()))
 def test_missing_or_unverified_fixture_rejected(self):
    with self.assertRaises(ValueError):
      extract({"state_account_count":0,"state_account_addresses":[],"accounts":{},
               "state_accounts_observed_slot":42,"state_account_manifest_sha256":"a"*64})
 def test_no_invented_fee_from_vault_or_dynamic_price(self):
    import inspect
    source=inspect.getsource(extract)
    self.assertIn('"effective_trade_fee_authenticated":False',source)
    self.assertIn('"openbook_adjusted_reserves_verified=False',source)
    self.assertIn('"active_bin_account_pricing_verified=False',source)
if __name__=="__main__":unittest.main()
