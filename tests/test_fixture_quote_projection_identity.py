import unittest
from unittest.mock import patch
from arb.fixture_config_quote_projection import derive
class Tests(unittest.TestCase):
    def pools(self):
        return [{"venue":"raydium_cpmm","address":"p","mints":["A","B"],
                 "snapshot_slot":12,"decoded_pool_state":{"amm_config":"cfg"}},
                {"venue":"raydium_amm_v4","address":"q","mints":["A","B"],
                 "snapshot_slot":12,"decoded_pool_state":{}}]
    def native(self):
        return [{"venue":p["venue"],"address":p["address"],"mints":p["mints"],
                 "snapshot_slot":p["snapshot_slot"],"vault_base_units":[300,400]}
                for p in self.pools()]
    def run_derive(self,native,fee=None):
        with patch("arb.fixture_config_quote_projection.extract_pool_states",return_value=self.pools()),patch(
             "arb.fixture_config_quote_projection.extract",return_value={"fundamentals":native}),patch(
             "arb.fixture_config_quote_projection.decode_native_config_fee",
             return_value=fee or {"venue":"raydium_cpmm","config_address":"cfg",
               "total_effective_fee_authenticated":False,"effective_quote_fee_ppm":None}):
            return derive({},observed_unix=100)
    def test_shuffled_fundamentals_rejoined_by_identity(self):
        r=self.run_derive(list(reversed(self.native())))
        self.assertEqual([x["address"] for x in r["snapshots"]],["p","q"])
        self.assertFalse(r["full_seven_venue_pricing_verified"])
    def test_duplicate_native_identity_rejected(self):
        with self.assertRaisesRegex(ValueError,"identities diverge"):
            self.run_derive([self.native()[0]]*2)
    def test_wrong_native_mint_rejected(self):
        native=self.native();native[0]["mints"]=["A","C"]
        with self.assertRaisesRegex(ValueError,"mint or slot mismatch"):
            self.run_derive(native)
    def test_wrong_fee_config_rejected(self):
        fee={"venue":"raydium_cpmm","config_address":"other","total_effective_fee_authenticated":True,
             "effective_quote_fee_ppm":2500}
        with self.assertRaisesRegex(ValueError,"not bound"):
            self.run_derive(self.native(),fee)
    def test_unverified_effective_fee_never_projected(self):
        fee={"venue":"raydium_cpmm","config_address":"cfg","total_effective_fee_authenticated":False,
             "effective_quote_fee_ppm":2500}
        with self.assertRaisesRegex(ValueError,"unverified effective fee"):
            self.run_derive(self.native(),fee)
    def test_missing_effective_fee_never_authenticated(self):
        fee={"venue":"raydium_cpmm","config_address":"cfg","total_effective_fee_authenticated":True,
             "effective_quote_fee_ppm":None}
        with self.assertRaisesRegex(ValueError,"ppm missing"):
            self.run_derive(self.native(),fee)
if __name__=="__main__":unittest.main()
