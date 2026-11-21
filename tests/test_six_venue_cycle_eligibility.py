"""2–6 leg source-identity cycle boundaries."""
import unittest
from arb.six_venue_cycle_eligibility import screen_cycle_source_eligibility

VENUES=["orca","raydium_cpmm","meteora_damm_v2","pumpswap","meteora_dlmm","raydium_clmm"]
def fixture(n):
    tokens=[f"T{i}" for i in range(n)]+["T0"]
    legs=[{"venue":VENUES[i],"pool":f"P{i}",
           "input_mint":tokens[i],"output_mint":tokens[i+1]} for i in range(n)]
    source=[{"venue":r["venue"],"address":r["pool"],
             "mints":[r["input_mint"],r["output_mint"]],
             "source_identity_refreshed":True,"current_source_slot":123,
             "current_complete_fee_and_tick_state_verified":False,
             "current_native_sdk_signed_quote_verified":False,
             "coordinator_eligible":False} for r in legs]
    report={"status":"FRESH_IDENTITY_ONLY_NOT_USABLE_REGISTRY_ADMISSION",
            "source_authenticated":source,"coordinator_eligible_count":0,
            "actionable":False,"live_execution_approved":False,"broadcast":False}
    return legs,tokens,report

class CycleEligibilityTests(unittest.TestCase):
    def test_two_through_six_leg_source_eligible_not_routable(self):
        for n in range(2,7):
            with self.subTest(n=n):
                a,b,c=fixture(n)
                checked=screen_cycle_source_eligibility(a,b,c)
                self.assertEqual(checked["legs"],n)
                self.assertFalse(checked["coordinator_eligible"])
                self.assertFalse(checked["signed_full_route_verified"])
    def test_unknown_unsigned_pool_rejected(self):
        a,b,c=fixture(3)
        del c["source_authenticated"][1]
        with self.assertRaisesRegex(ValueError,"unsigned"):
            screen_cycle_source_eligibility(a,b,c)
    def test_fee_and_quote_not_silently_promoted(self):
        a,b,c=fixture(2)
        c["source_authenticated"][0]["current_native_sdk_signed_quote_verified"]=True
        with self.assertRaisesRegex(ValueError,"untrusted"):
            screen_cycle_source_eligibility(a,b,c)
    def test_repeated_pool_rejected(self):
        a,b,c=fixture(2)
        a[1]["venue"],a[1]["pool"]=a[0]["venue"],a[0]["pool"]
        a[1]["input_mint"],a[1]["output_mint"]="T1","T0"
        with self.assertRaisesRegex(ValueError,"repeated"):
            screen_cycle_source_eligibility(a,b,c)
    def test_disconnected_cycle_rejected(self):
        a,b,c=fixture(4)
        a[2]["input_mint"]="wrong"
        with self.assertRaisesRegex(ValueError,"disconnected"):
            screen_cycle_source_eligibility(a,b,c)
    def test_untrusted_fresh_report_rejected(self):
        a,b,c=fixture(2)
        c["actionable"]=True
        with self.assertRaisesRegex(ValueError,"fresh"):
            screen_cycle_source_eligibility(a,b,c)

if __name__=="__main__":
    unittest.main()
