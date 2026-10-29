import unittest
from arb.pumpswap_signed_parity import run


def fixture():
    pool="P"*32
    mint0="A"*32
    mint1="B"*32
    trials=[{"input_mint":mint,"amount_in":n,"official_sdk_output":"200",
             "python_candidate_output":"200","status":"OFFICIAL_SDK_CANDIDATE_EXACT"}
            for mint in (mint0,mint1) for n in (10000,100000)]
    sdk={"venue":"pumpswap","pools":[{"address":pool,"source_slot":42,
         "source_digest":"a"*64,"trials":trials}]}
    manifest={"venue":"pumpswap","trials":[{
        "pool":pool,"input_mint":t["input_mint"],"amount_in":t["amount_in"],
        "source_slot":42,"source_digest":"a"*64,
        "output_mint":mint1 if t["input_mint"]==mint0 else mint0,
        "input_token_account":"C"*32,"output_token_account":"D"*32,
        "signed_transaction_base64":"AQ=="
    } for t in trials]}
    return sdk,manifest


class PumpSwapSignedParitySafetyTests(unittest.TestCase):
    def test_no_remote_rpc_even_with_valid_manifest(self):
        sdk,manifest=fixture()
        with self.assertRaisesRegex(ValueError,"localhost"):
            run("https://api.mainnet-beta.solana.com",sdk,manifest)

    def test_missing_signed_trial_fails_before_execution(self):
        sdk,manifest=fixture()
        manifest["trials"].pop()
        with self.assertRaisesRegex(ValueError,"missing or duplicate signed trial"):
            run("http://127.0.0.1:8899",sdk,manifest)

    def test_changed_source_digest_fails_before_execution(self):
        sdk,manifest=fixture()
        manifest["trials"][0]["source_digest"]="b"*64
        with self.assertRaisesRegex(ValueError,"source identity mismatch"):
            run("http://127.0.0.1:8899",sdk,manifest)

    def test_duplicate_trial_fails_before_execution(self):
        sdk,manifest=fixture()
        manifest["trials"].append(dict(manifest["trials"][0]))
        with self.assertRaisesRegex(ValueError,"duplicate signed trial"):
            run("http://127.0.0.1:8899",sdk,manifest)

    def test_indicative_price_cannot_start_signed_execution(self):
        sdk,manifest=fixture()
        sdk["pools"][0]["trials"][0]["status"]="UNVERIFIED_NATIVE_FORMULA_CANDIDATE"
        with self.assertRaisesRegex(ValueError,"official SDK did not verify"):
            run("http://127.0.0.1:8899",sdk,manifest)


if __name__=="__main__":
    unittest.main()
