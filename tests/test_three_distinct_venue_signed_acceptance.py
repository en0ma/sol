import unittest
from unittest.mock import patch
from arb.m5_three_distinct_venue_signed_acceptance import verify
class Tests(unittest.TestCase):
    def source(self):
        return {"fixture_kind":"THREE_DISTINCT_VENUE_CLOSED_ROUTE",
        "source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
        "route_venues":["orca","raydium_cpmm","raydium_amm_v4"],
        "route_pool_addresses":["p","q","r"],
        "route_mints":["A","B","C","A"],"state_account_manifest_sha256":"digest"}
    def receipt(self):
        s=self.source()
        return {"status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
            "legs":3,"route_venues":s["route_venues"],
            "route_pool_addresses":s["route_pool_addresses"],"route_mints":s["route_mints"],
            "state_account_manifest_sha256":"digest",
            "signed_cpi_per_leg_verified":True,
            "signed_atomic_simulation_verified":True,
            "rollback_failure_case_verified":True,
            "negative_failure_instruction_index":2,
            "planned_inputs":[10,9,8],
            "positive_post_balances_base_units":[0,0,0,12],
            "actionable":False,"live_execution_approved":False,"broadcast":False}
    @patch("arb.source_snapshot_manifest.verify",return_value=True)
    def test_positive(self,_):
        self.assertTrue(verify(self.source(),self.receipt())["accepted"])
    @patch("arb.source_snapshot_manifest.verify",return_value=True)
    def test_fake_success_rejected(self,_):
        for key,value in (("signed_cpi_per_leg_verified",False),
                ("rollback_failure_case_verified",False),
                ("negative_failure_instruction_index",1),
                ("positive_post_balances_base_units",[0,1,0,12]),
                ("broadcast",True)):
            with self.subTest(key=key):
                r=self.receipt();r[key]=value
                with self.assertRaises(ValueError):verify(self.source(),r)
if __name__=="__main__":unittest.main()
