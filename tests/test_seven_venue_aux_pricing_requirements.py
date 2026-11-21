import unittest
from arb.seven_venue_aux_pricing_requirements import REQUIRED,requirements
from arb.execution_target_matrix import TARGET_VENUES
class Tests(unittest.TestCase):
 def test_every_active_venue_has_specific_auxiliary_account_requirements(self):
    self.assertEqual(set(REQUIRED),set(TARGET_VENUES))
    self.assertTrue(all(REQUIRED[v] for v in TARGET_VENUES))
 def test_invalid_source_never_completes_requirements(self):
    with self.assertRaises(ValueError):requirements({})
 def test_no_fee_and_auxiliary_verification_claims(self):
    import inspect
    s=inspect.getsource(requirements)
    self.assertIn('"account_derived_auxiliary_models_verified":0',s)
    self.assertIn('"quote_accuracy_verified":False',s)
if __name__=="__main__":unittest.main()
