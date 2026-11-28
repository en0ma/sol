"""Synthetic boundary checks for official SDK transport; not execution evidence."""
import base64
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from arb.meteora_damm_v2_native_quote import quote_pool_account, PROGRAM

class SdkResultTests(unittest.TestCase):
    def test_full_amount_and_revision_binding(self):
        account={"owner":PROGRAM,"executable":False,"data":[base64.b64encode(b"pool").decode(),"base64"]}
        result={"status":"OFFICIAL_METEORA_DAMM_V2_EXACT_INPUT",
                "official_repository_revision":"5398b5c7c534de014091132da37c6478cce671a8",
                "amount_in":100,"amount_out":90,"amount_left":0,
                "actionable":False,"broadcast":False,"live_execution_approved":False}
        args=dict(mint_in="a",amount_in=100,fork_unix_timestamp=1,fork_clock_slot=2)
        with patch("arb.meteora_damm_v2_native_quote.decode",return_value={"token_a_mint":"a","token_b_mint":"b"}), \
             patch("arb.meteora_damm_v2_native_quote.subprocess.run") as run:
            run.return_value=SimpleNamespace(returncode=0,stdout=json.dumps(result))
            self.assertEqual(quote_pool_account(account,**args)["amount_out"],90)
            for change in ({"amount_left":1},{"amount_in":99},{"official_repository_revision":"wrong"},{"broadcast":True}):
                run.return_value=SimpleNamespace(returncode=0,stdout=json.dumps({**result,**change}))
                with self.assertRaisesRegex(ValueError,"incomplete or inconsistent"):
                    quote_pool_account(account,**args)

if __name__=="__main__":unittest.main()
