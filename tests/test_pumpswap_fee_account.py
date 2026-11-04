import unittest
from unittest.mock import patch
from arb.pumpswap_fee_account import ADDRESS, PROGRAM, decode_authenticated


class PumpFeeAccountAuthTests(unittest.TestCase):
    @patch("arb.pumpswap_fee_account.authenticated_address",return_value=(ADDRESS,4))
    @patch("arb.pumpswap_fee_account.decode")
    def test_valid_owner_pda_bump_is_authenticated_not_effective(self, decode, derived):
        decode.return_value={"bump":4,"effective_fee_verified":False}
        account={"owner":PROGRAM,"executable":False,"data":["AA==","base64"]}
        value=decode_authenticated(account,address=ADDRESS)
        self.assertTrue(value["account_authenticated"])
        self.assertFalse(value["effective_fee_verified"])

    @patch("arb.pumpswap_fee_account.authenticated_address",return_value=(ADDRESS,4))
    def test_mismatched_owner_or_address_fail_closed(self, derived):
        account={"owner":"another-program","executable":False,"data":["AA==","base64"]}
        with self.assertRaisesRegex(ValueError,"unauthenticated"):
            decode_authenticated(account,address=ADDRESS)
        account["owner"]=PROGRAM
        with self.assertRaisesRegex(ValueError,"unauthenticated"):
            decode_authenticated(account,address="bad")

    @patch("arb.pumpswap_fee_account.authenticated_address",return_value=(ADDRESS,4))
    @patch("arb.pumpswap_fee_account.decode",return_value={"bump":3})
    def test_bump_mismatch_fails_closed(self, decode, derived):
        with self.assertRaisesRegex(ValueError,"bump mismatch"):
            decode_authenticated({"owner":PROGRAM,"executable":False,
                                  "data":["AA==","base64"]},address=ADDRESS)
