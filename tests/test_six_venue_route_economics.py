"""Exact integer arithmetic and missing-cost fail-closed cases."""
import unittest
from arb.six_venue_route_economics import assess_offline_cycle_costs

def receipt(n=3):
    return {"legs":n,"start_mint":"WSOL","initial_base_units":100000,
            "terminal_base_units":101000,"independent_signed_accepted":True,
            "closed_route_verified":True,"signed_cpi_per_leg_verified":True,
            "signed_spl_poststate_verified":True,"rollback_control_verified":True,
            "offline_only":True,"actionable":False,
            "live_execution_approved":False,"broadcast":False}
class CostTests(unittest.TestCase):
    def test_each_route_length_is_supported_but_never_actionable(self):
        for n in range(2,7):
            with self.subTest(n=n):
                r=assess_offline_cycle_costs(receipt(n))
                self.assertEqual(r["observed_gross_base_units"],1000)
                self.assertIsNone(r["net_base_units"])
                self.assertFalse(r["actionable"])
    def test_costs_must_be_explicit_verified_same_mint_units(self):
        r=receipt()
        r["network_fee_conversion_independently_verified"]=True
        r["verified_costs_start_mint_base_units"]={
            "network_fee":200,"priority_fee":350,"setup_rent_net":0,
            "flash_loan_fee":0,"tip":0,"other":0}
        out=assess_offline_cycle_costs(r)
        self.assertEqual(out["net_base_units"],450)
        self.assertTrue(out["net_positive_arithmetic"])
        self.assertFalse(out["future_live_profitability_verified"])
        r["verified_costs_start_mint_base_units"]["tip"]=700
        self.assertEqual(assess_offline_cycle_costs(r)["net_base_units"],-250)
    def test_incomplete_costs_cannot_claim_net(self):
        r=receipt()
        r["network_fee_conversion_independently_verified"]=True
        r["verified_costs_start_mint_base_units"]={"network_fee":1}
        self.assertIsNone(assess_offline_cycle_costs(r)["net_base_units"])
    def test_unsigned_or_missing_rollback_rejected(self):
        for field in ("independent_signed_accepted","signed_cpi_per_leg_verified",
                      "rollback_control_verified","offline_only"):
            with self.subTest(field=field):
                r=receipt();r[field]=False
                with self.assertRaisesRegex(ValueError,"incomplete"):
                    assess_offline_cycle_costs(r)
    def test_float_and_bool_values_rejected(self):
        for value in (10.5,True,-1,2**64):
            r=receipt();r["terminal_base_units"]=value
            with self.assertRaises(ValueError):assess_offline_cycle_costs(r)
    def test_no_mainnet_permission(self):
        r=receipt();r["broadcast"]=True
        with self.assertRaises(ValueError):assess_offline_cycle_costs(r)

if __name__=="__main__":
    unittest.main()
