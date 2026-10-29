import unittest
from arb.m5_venue_pool_registry_expansion import promote_signed


def fixture():
    venues=(
        ("orca","ORCA_NEW_POOLS_SIGNED_VERIFIED","ORCA_NEW_POOL_SIGNED_EXACT",
         ("a_to_b","b_to_a"),("signed_spl_output","official_core_output","local_native_output")),
        ("meteora_damm_v2","METEORA_DAMM_V2_CONFIGURED_POOLS_SIGNED_VERIFIED",
         "METEORA_DAMM_V2_OFFICIAL_SIGNED_EXACT",("a_to_b","b_to_a"),
         ("signed_output","official_output")),
        ("raydium_cpmm","RAYDIUM_CPMM_SIGNED_VERIFIED",
         "RAYDIUM_CPMM_SIGNED_NATIVE_EXACT",("0_to_1","1_to_0"),
         ("signed_output","native_output")))
    candidates={"pools":[]}
    ray_candidates={"pools":[]}
    receipts={}
    for venue,status,trial_status,directions,outs in venues:
        pool=venue+"_"+"x"*33
        (ray_candidates if venue=="raydium_cpmm" else candidates)["pools"].append(
            {"venue":venue,"address":pool,"mints":["A","B"]})
        trials=[]
        for direction in directions:
            for amount in (100,1000):
                trial={"pool":pool,"direction":direction,"status":trial_status,
                       "amount_in":amount,"signed_sha256":"a"*64}
                trial.update({key:42 for key in outs})
                if venue=="raydium_cpmm":trial["signature"]="1"*88
                trials.append(trial)
        receipts[venue]={"status":status,"pools":[{
            "pool":pool,"verified":True,"exact_matches":4,
            "trials":trials}]}
    pump="PumpExamplePool"
    snapshot={"venue":"pumpswap","pools":[{
        "address":pump,"mints":["MintOne","MintTwo"],
        "status":"AUTHENTICATED_SOURCE_ONLY","verified_snapshot_slot":72,
        "authenticated_source_sha256":"b"*64}]}
    independent={"venue":"pumpswap",
        "status":"INDEPENDENT_SIGNED_NATIVE_SDK_SPL_PARITY",
        "signed_parity_verified":True,"independent_signed_audit_verified":True,
        "verified_pools":1,"actionable":False,"broadcast":False,
        "registry_admission_approved":False,
        "pools":[{"pool":pump,"four_genuine_signed_trials_audited":True,
            "source_slot":72,"source_digest":"b"*64,
            "signed_transaction_hashes":[str(i)*64 for i in range(1,5)]}]}
    return candidates,ray_candidates,receipts,snapshot,independent


def promote(data, *,pump=True,registry=None):
    c,rc,r,source,independent=data
    return promote_signed(registry if registry is not None else
        {"pools":[{"venue":"pumpswap","address":"PumpExamplePool",
                   "mints":["MintOne","MintTwo"]}]},
        c,r["orca"],r["meteora_damm_v2"],raydium_candidates=rc,
        raydium_receipt=r["raydium_cpmm"],required=1,
        pumpswap_candidates=source if pump else None,
        pumpswap_receipt=independent if pump else None,pumpswap_required=1)


class PumpSwapSignedAdmissionTest(unittest.TestCase):
    def test_existing_registry_hint_gains_durable_signed_provenance(self):
        result=promote(fixture())
        pump=[p for p in result["pools"] if p["venue"]=="pumpswap"]
        self.assertEqual(len(pump),1)
        proof=pump[0]["signed_provenance"]
        self.assertEqual(proof["source_slot"],72)
        self.assertEqual(len(proof["signed_transaction_hashes"]),4)
        self.assertEqual(len(proof["independent_receipt_sha256"]),64)
        self.assertEqual(promote(fixture(),registry=result),result)

    def test_sdk_only_receipt_cannot_be_promoted(self):
        data=list(fixture())
        data[4]["status"]="SDK_CANDIDATE_PRICE_PARITY_ONLY"
        with self.assertRaisesRegex(ValueError,"independent signed audit"):
            promote(data)

    def test_changed_source_digest_rejected(self):
        data=list(fixture())
        data[4]["pools"][0]["source_digest"]="c"*64
        with self.assertRaisesRegex(ValueError,"source snapshot provenance"):
            promote(data)

    def test_duplicate_signed_transaction_rejected(self):
        data=list(fixture())
        data[4]["pools"][0]["signed_transaction_hashes"]=["1"*64]*4
        with self.assertRaisesRegex(ValueError,"unique four signed"):
            promote(data)

    def test_missing_corresponding_source_rejected(self):
        data=list(fixture())
        data[3]["pools"][0]["status"]="SOURCE_REJECTED"
        with self.assertRaisesRegex(ValueError,"unverified source"):
            promote(data)

    def test_fourth_venue_does_not_weaken_existing_three_requirements(self):
        data=list(fixture())
        data[2]["orca"]["pools"][0]["trials"].pop()
        with self.assertRaisesRegex(ValueError,"four signed trials"):
            promote(data)


if __name__=="__main__":
    unittest.main()
