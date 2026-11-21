"""Registry admission never upgrades unverified pool hints into topology."""
import unittest
from arb.m5_registry_capacity import admit,MAX_REGISTRY_POOLS
from arb.m5_start_mint_expansion import topology

def old(venue,address,a,b):
    return {"venue":venue,"address":address,"mints":[a,b]}

def verified(venue,address,a,b):
    return {**old(venue,address,a,b),
            "source_verified_only":True,"source_verified_slot":123}

class RegistryCapacityTests(unittest.TestCase):
    def test_expanded_pool_ceiling_accepts_valid_verified_candidates(self):
        existing=[old("orca","first","A","B")]
        candidates=[verified("raydium_cpmm",str(i),"X"+str(i),"Y"+str(i))
                    for i in range(520)]
        evidence=admit(existing,candidates,maximum=MAX_REGISTRY_POOLS)
        self.assertEqual(evidence["admitted_count"],520)
        self.assertEqual(evidence["unadmitted_count"],0)
        self.assertEqual(evidence["registry_capacity"],768)
        self.assertTrue(evidence["source_reverification_required"])
        self.assertFalse(evidence["actionable"])

    def test_when_capacity_scarce_prioritizes_new_triangle_start(self):
        existing=[old("orca","ab","A","B"),
                  old("meteora_damm_v2","bc","B","C")]
        options=[verified("raydium_cpmm","irrelevant","X","Y"),
                 verified("raydium_cpmm","closes","C","A")]
        result=admit(existing,options,maximum=3)
        self.assertEqual([x["address"] for x in result["admitted"]],
                         ["closes"])
        self.assertEqual(result["unadmitted_count"],1)
        self.assertEqual(topology(existing+result["admitted"])[
            "three_hop_start_mint_count"],3)

    def test_rejects_unauthenticated_and_forged_source_slot(self):
        existing=[old("orca","ab","A","B")]
        for candidate in (
                old("raydium_cpmm","unverified","B","C"),
                {**verified("raydium_cpmm","wrong-slot","B","C"),
                 "source_verified_slot":True},
                {**verified("raydium_cpmm","wrong-status","B","C"),
                 "source_verified_only":False}):
            with self.assertRaisesRegex(ValueError,"source-verified"):
                admit(existing,[candidate])
        with self.assertRaisesRegex(ValueError,"invalid bounded"):
            admit(existing,[],maximum=769)

    def test_duplicate_pool_never_admitted_twice(self):
        existing=[old("orca","same","A","B")]
        candidate=verified("orca","same","A","B")
        result=admit(existing,[candidate,candidate])
        self.assertEqual(result["admitted_count"],0)
        self.assertEqual(result["unadmitted_count"],0)

if __name__=="__main__":
    unittest.main()
