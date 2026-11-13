import unittest
from unittest.mock import patch

from arb.pumpswap_native_source_capture import capture


POOL="A"*32
MINT_A="B"*32
MINT_B="C"*32
REG={"pools":[{"venue":"pumpswap","address":POOL,"mints":[MINT_A,MINT_B]}]}


class PumpSwapFourthVenueCaptureTests(unittest.TestCase):
    def test_not_an_execution_admission_receipt(self):
        import base64
        from arb.pumpswap_pool import PROGRAM
        state={"base_mint":MINT_A,"quote_mint":MINT_B}
        account={"owner":PROGRAM,"executable":False,"data":[base64.b64encode(b"snapshot").decode(),"base64"]}
        verified={"verified":True,"slot":12,"fee_mode_diagnostic":{"status":"FEE_MODE_AMBIGUOUS"},
                  "authenticated_source_accounts":[{"address":POOL,"owner":PROGRAM,"account_base64":"AA=="}]+[
                      {"address":str(i),"owner":PROGRAM,"account_base64":"AA=="} for i in range(5)]}
        with patch("arb.pumpswap_native_source_capture.call",return_value={"value":account,"context":{"slot":11}}), patch(
            "arb.pumpswap_native_source_capture.decode",return_value=state),patch(
            "arb.pumpswap_native_source_capture.verify",return_value=verified):
            report=capture("http://127.0.0.1:8899",REG,limit=1)
        self.assertEqual(report["authenticated"],1)
        self.assertEqual(len(report["pools"][0]["authenticated_source_sha256"]),64)
        self.assertEqual(report["pools"][0]["source_fee_mode"],"FEE_MODE_AMBIGUOUS")
        self.assertEqual(len(report["pools"][0]["native_quote_candidates"]),4)
        self.assertTrue(all(not x["signed_parity_verified"] for x in report["pools"][0]["native_quote_candidates"]))
        for name in ("actionable","broadcast","native_pricing_verified",
                     "signed_parity_verified","registry_admission_approved"):
            self.assertIs(report[name],False)
    def test_transient_live_pool_state_change_retries_same_slot_verifier(self):
        from arb.pumpswap_native_source_capture import stable_source_snapshot
        import base64
        from arb.pumpswap_pool import PROGRAM
        state={"base_mint":MINT_A,"quote_mint":MINT_B}
        account={"owner":PROGRAM,"executable":False,
                 "data":[base64.b64encode(b"snapshot").decode(),"base64"]}
        response={"value":account,"context":{"slot":11}}
        verified={"verified":True,"slot":12}
        with patch("arb.pumpswap_native_source_capture.call",return_value=response),patch(
            "arb.pumpswap_native_source_capture.decode",return_value=state),patch(
            "arb.pumpswap_native_source_capture.verify",
            side_effect=[ValueError("PumpSwap pool owner or state changed"),verified]) as check:
            slot,pool,authenticated=stable_source_snapshot(
                "https://readonly.example.com",POOL,[MINT_A,MINT_B])
        self.assertEqual(slot,11)
        self.assertEqual(authenticated["slot"],12)
        self.assertEqual(check.call_count,2)

    def test_persistent_live_pool_state_change_never_admits_source(self):
        from arb.pumpswap_native_source_capture import stable_source_snapshot
        import base64
        from arb.pumpswap_pool import PROGRAM
        account={"owner":PROGRAM,"executable":False,
                 "data":[base64.b64encode(b"snapshot").decode(),"base64"]}
        with patch("arb.pumpswap_native_source_capture.call",
                   return_value={"value":account,"context":{"slot":11}}),patch(
            "arb.pumpswap_native_source_capture.decode",
            return_value={"base_mint":MINT_A,"quote_mint":MINT_B}),patch(
            "arb.pumpswap_native_source_capture.verify",
            side_effect=ValueError("PumpSwap pool owner or state changed")) as check:
            with self.assertRaisesRegex(ValueError,"pool owner or state changed"):
                stable_source_snapshot("https://readonly.example.com",POOL,[MINT_A,MINT_B])
        self.assertEqual(check.call_count,4)

    def test_rejects_incomplete_proof_of_same_slot_source_accounts(self):
        import base64
        from arb.pumpswap_pool import PROGRAM
        state={"base_mint":MINT_A,"quote_mint":MINT_B}
        account={"owner":PROGRAM,"executable":False,"data":[base64.b64encode(b"snapshot").decode(),"base64"]}
        verified={"verified":True,"slot":12,
                  "authenticated_source_accounts":[],
                  "fee_mode_diagnostic":{"status":"FEE_MODE_AMBIGUOUS"}}
        with patch("arb.pumpswap_native_source_capture.call",return_value={"value":account,"context":{"slot":11}}),patch(
            "arb.pumpswap_native_source_capture.decode",return_value=state),patch(
            "arb.pumpswap_native_source_capture.verify",return_value=verified):
            report=capture("http://127.0.0.1:8899",REG,limit=1)
        self.assertEqual(report["authenticated"],0)
        self.assertEqual(report["pools"][0]["status"],"SOURCE_REJECTED")

    def test_rejects_duplicate_authenticated_source_account(self):
        import base64
        from arb.pumpswap_pool import PROGRAM
        account={"owner":PROGRAM,"executable":False,
                 "data":[base64.b64encode(b"snapshot").decode(),"base64"]}
        sources=[{"address":POOL,"owner":PROGRAM,"account_base64":"AA=="} for _ in range(6)]
        verified={"verified":True,"slot":12,"authenticated_source_accounts":sources,
                  "fee_mode_diagnostic":{"status":"FEE_MODE_AMBIGUOUS"}}
        with patch("arb.pumpswap_native_source_capture.call",
                   return_value={"value":account,"context":{"slot":11}}),patch(
            "arb.pumpswap_native_source_capture.decode",
            return_value={"base_mint":MINT_A,"quote_mint":MINT_B}),patch(
            "arb.pumpswap_native_source_capture.verify",return_value=verified):
            report=capture("http://127.0.0.1:8899",REG,limit=1)
        self.assertEqual(report["authenticated"],0)
        self.assertIn("duplicate",report["pools"][0]["reason"])

    def test_rejects_mint_identity_change(self):
        import base64
        from arb.pumpswap_pool import PROGRAM
        account={"owner":PROGRAM,"executable":False,"data":[base64.b64encode(b"snapshot").decode(),"base64"]}
        with patch("arb.pumpswap_native_source_capture.call",return_value={"value":account,"context":{"slot":11}}),patch(
            "arb.pumpswap_native_source_capture.decode",return_value={"base_mint":"D"*32,"quote_mint":MINT_B}):
            report=capture("http://127.0.0.1:8899",REG,limit=1)
        self.assertEqual(report["authenticated"],0)
        self.assertEqual(report["pools"][0]["status"],"SOURCE_REJECTED")
    def test_no_public_discovery_and_bounded_sample(self):
        with self.assertRaisesRegex(ValueError,"bounded"):
            capture("http://127.0.0.1:8899",REG,limit=11)
        with self.assertRaisesRegex(ValueError,"insufficient"):
            capture("http://127.0.0.1:8899",REG,limit=2)


if __name__=="__main__":
    unittest.main()
