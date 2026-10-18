import base64
import unittest
from unittest.mock import patch
from solders.pubkey import Pubkey
from arb.orca_swap_v2_local_token_accounts import (
    require_loopback_rpc,observe_token_account,TOKEN_PROGRAMS
)

class LocalTokenAccountTests(unittest.TestCase):
    def test_only_loopback_allowed(self):
        self.assertEqual(require_loopback_rpc("http://127.0.0.1:8899"),"http://127.0.0.1:8899")
        for url in ("https://127.0.0.1:8899","http://rpc.example:8899",
                    "http://10.0.0.2:8899","http://localhost:8899",
                    "http://127.0.0.1:8899?x=y"):
            with self.subTest(url=url),self.assertRaises(ValueError):
                require_loopback_rpc(url)

    @patch("arb.orca_swap_v2_local_token_accounts.call")
    def test_mint_authority_state_verified_not_signer_control(self,rpc_call):
        mint=Pubkey.new_unique()
        authority=Pubkey.new_unique()
        raw=bytearray(165)
        raw[:32]=bytes(mint)
        raw[32:64]=bytes(authority)
        raw[108]=1
        program=next(iter(TOKEN_PROGRAMS))
        rpc_call.return_value={"context":{"slot":42},"value":{
            "owner":program,"data":[base64.b64encode(raw).decode(),"base64"]}}
        result=observe_token_account("http://127.0.0.1:8899",str(Pubkey.new_unique()),
                                     str(mint),str(authority),program)
        self.assertTrue(result["local_rpc_verified"])
        self.assertFalse(result["signer_control_verified"])
        self.assertFalse(result["actionable"])
        rpc_call.assert_called_once()
        with self.assertRaisesRegex(ValueError,"mismatch"):
            observe_token_account("http://127.0.0.1:8899",str(Pubkey.new_unique()),
                                  str(Pubkey.new_unique()),str(authority),program)

if __name__=="__main__":
    unittest.main()
