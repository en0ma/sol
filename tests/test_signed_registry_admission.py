import unittest
from arb.m5_venue_pool_registry_expansion import promote_signed

SPECS={
 "orca":("ORCA_NEW_POOLS_SIGNED_VERIFIED","ORCA_NEW_POOL_SIGNED_EXACT",("signed_spl_output","official_core_output","local_native_output"),"signed_sha256",("a_to_b","b_to_a")),
 "meteora_damm_v2":("METEORA_DAMM_V2_CONFIGURED_POOLS_SIGNED_VERIFIED","METEORA_DAMM_V2_OFFICIAL_SIGNED_EXACT",("signed_output","official_output"),"signed_sha256",("a_to_b","b_to_a")),
 "raydium_cpmm":("RAYDIUM_CPMM_SIGNED_VERIFIED","RAYDIUM_CPMM_SIGNED_NATIVE_EXACT",("signed_output","native_output"),"signature",("0_to_1","1_to_0")),
}
def fixture():
    candidates={"pools":[]};ray_candidates={"pools":[]};receipts={}
    for venue,(status,trial_status,outputs,proof,directions) in SPECS.items():
        pool=venue+"_"+"x"*33
        row={"venue":venue,"address":pool,"mints":["mint_a","mint_b"]}
        (ray_candidates if venue=="raydium_cpmm" else candidates)["pools"].append(row)
        trials=[]
        for d in directions:
            for amount in (100,1000):
                t={"status":trial_status,"pool":pool,"direction":d,("amount_in" if venue=="raydium_cpmm" else "input"):amount}
                t.update({k:42 for k in outputs})
                t[proof]="a"*64 if proof=="signed_sha256" else "1"*88
                trials.append(t)
        receipts[venue]={"status":status,"pools":[{"pool":pool,"verified":True,
                  "exact_matches":4,"exact":4,"trial_count":4,"trials":trials}]}
    return candidates,ray_candidates,receipts

class SignedRegistryAdmission(unittest.TestCase):
    def promote(self,mutate=None,registry=None):
        candidates,ray_candidates,receipts=fixture()
        if mutate:mutate(candidates,ray_candidates,receipts)
        return promote_signed(registry or {"pools":[]},candidates,
             receipts["orca"],receipts["meteora_damm_v2"],
             raydium_candidates=ray_candidates,raydium_receipt=receipts["raydium_cpmm"],required=1)
    def test_three_venues_admitted_only_after_exact_signed_proof(self):
        promoted=self.promote()
        self.assertEqual({p["venue"] for p in promoted["pools"]},set(SPECS))
        self.assertEqual(self.promote(registry=promoted),promoted)
    def test_missing_raydium_amount_rejected(self):
        with self.assertRaisesRegex(ValueError,"invalid input size"):
            self.promote(lambda a,b,r:r["raydium_cpmm"]["pools"][0]["trials"][0].pop("amount_in"))
    def test_missing_orca_digest_rejected(self):
        with self.assertRaisesRegex(ValueError,"transaction evidence"):
            self.promote(lambda a,b,r:r["orca"]["pools"][0]["trials"][0].pop("signed_sha256"))
    def test_missing_signature_rejected(self):
        with self.assertRaisesRegex(ValueError,"transaction evidence"):
            self.promote(lambda a,b,r:r["raydium_cpmm"]["pools"][0]["trials"][0].pop("signature"))
    def test_forged_exact_counter_rejected(self):
        with self.assertRaisesRegex(ValueError,"outputs differ"):
            self.promote(lambda a,b,r:r["orca"]["pools"][0]["trials"][0].update({"signed_spl_output":43}))
    def test_duplicate_direction_does_not_pass(self):
        with self.assertRaisesRegex(ValueError,"duplicate signed trial"):
            self.promote(lambda a,b,r:r["meteora_damm_v2"]["pools"][0]["trials"][1].update({"input":100}))
    def test_unlisted_pool_rejected(self):
        with self.assertRaisesRegex(ValueError,"absent from authenticated"):
            self.promote(lambda a,b,r:b["pools"].clear())
    def test_missing_venue_receipt_rejected(self):
        with self.assertRaisesRegex(ValueError,"missing or failed"):
            self.promote(lambda a,b,r:r["raydium_cpmm"].update({"status":"RAYDIUM_CPMM_SIGNED_INCOMPLETE"}))
    def test_pool_identity_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,"identity mismatch"):
            self.promote(lambda a,b,r:r["orca"]["pools"][0]["trials"][0].update({"pool":"fake"}))
    def test_unverified_rejected(self):
        with self.assertRaisesRegex(ValueError,"fewer than required"):
            self.promote(lambda a,b,r:r["raydium_cpmm"]["pools"][0].update({"verified":False}))
    def test_missing_raydium_manifest_rejected(self):
        with self.assertRaisesRegex(ValueError,"all three venues"):
            c,rc,r=fixture()
            promote_signed({"pools":[]},c,r["orca"],r["meteora_damm_v2"],raydium_receipt=r["raydium_cpmm"],required=1)

if __name__=="__main__":
    unittest.main()
