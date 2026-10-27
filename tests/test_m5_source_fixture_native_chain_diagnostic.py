import unittest
from unittest.mock import patch
from arb.m5_source_fixture_native_chain_diagnostic import inspect_fixture

class FixtureNativeChainTests(unittest.TestCase):
    def fixture(self):
        return {"route_mints":["A","B","C","A"],
                "state_accounts_observed_slot":9}
    def rows(self):
        return [{"venue":v,"address":p,"snapshot_slot":9} for v,p in
                (("orca","one"),("meteora_dlmm","two"),("pumpswap","three"))]
    @patch("arb.m5_source_fixture_native_chain_diagnostic.fixture_quote_leg")
    @patch("arb.m5_source_fixture_native_chain_diagnostic.extract_pool_states")
    def test_real_adapter_blockers_preserved_without_fake_completed_quote(self,states,quote):
        states.return_value=self.rows()
        quote.return_value={"quote_status":"NATIVE_QUOTE_BLOCKED",
                            "reason":"MISSING_NATIVE_AUXILIARY_STATE"}
        result=inspect_fixture(self.fixture(),observed_unix=100,amounts=(100,1000))
        self.assertEqual(result["attempt_count"],2)
        self.assertEqual(result["full_native_quote_count"],0)
        self.assertEqual(result["net_profitable_verified_count"],0)
        self.assertIn("MISSING_NATIVE_AUXILIARY_STATE",result["attempts"][0]["reason"])
        self.assertFalse(result["broadcast"])
        self.assertEqual(quote.call_count,2)
    @patch("arb.m5_source_fixture_native_chain_diagnostic.fixture_quote_leg")
    @patch("arb.m5_source_fixture_native_chain_diagnostic.extract_pool_states")
    def test_indicative_existing_adapter_cannot_be_upgraded(self,states,quote):
        states.return_value=self.rows()
        quote.return_value={"quote_status":"SOURCE_BOUND_INDICATIVE",
                            "predicted_output_base_units":200}
        result=inspect_fixture(self.fixture(),observed_unix=100,amounts=(100,))
        self.assertEqual(result["full_native_quote_count"],0)
        self.assertIn("indicative only",result["attempts"][0]["reason"])
        self.assertFalse(result["fixture_native_protocol_exact_verified"])
    @patch("arb.m5_source_fixture_native_chain_diagnostic.extract_pool_states")
    def test_nonclosed_source_triangle_refused(self,states):
        states.return_value=self.rows()
        fixture=self.fixture()
        fixture["route_mints"][-1]="X"
        with self.assertRaisesRegex(ValueError,"closed source triangle"):
            inspect_fixture(fixture,observed_unix=100)

if __name__=="__main__":unittest.main()
