import base64
import unittest
from unittest.mock import patch
from solders.pubkey import Pubkey
from arb.meteora_dlmm_bin_preflight import verify_pool_oracle,ORACLE_DISC
from arb.meteora_dlmm import PROGRAM

KEY=str(Pubkey.new_unique())

def payload(index=1,active=2,capacity=10,owner=PROGRAM):
    raw=ORACLE_DISC+index.to_bytes(8,"little")+active.to_bytes(8,"little")+capacity.to_bytes(8,"little")+bytes(64)
    return {"value":{"owner":owner,"executable":False,"data":[base64.b64encode(raw).decode(),"base64"]}}

class DlmmOracleAuthenticationTests(unittest.TestCase):
    @patch("arb.meteora_dlmm_bin_preflight.call")
    def test_authentic_oracle_account(self,rpc):
        rpc.return_value=payload()
        result=verify_pool_oracle("http://127.0.0.1:8899",KEY)
        self.assertTrue(result["authenticated"])
        self.assertEqual(result["observation_capacity"],10)
        self.assertEqual(rpc.call_args.args[1],"getAccountInfo")

    @patch("arb.meteora_dlmm_bin_preflight.call")
    def test_wrong_owner_and_invalid_observations_fail(self,rpc):
        for fixture in [payload(owner=str(Pubkey.new_unique())),
                        payload(index=10),payload(active=11)]:
            rpc.return_value=fixture
            with self.assertRaises(ValueError):
                verify_pool_oracle("http://127.0.0.1:8899",KEY)

    @patch("arb.meteora_dlmm_bin_preflight.call")
    def test_remote_rpc_not_contacted(self,rpc):
        with self.assertRaises(ValueError):
            verify_pool_oracle("https://api.mainnet-beta.solana.com",KEY)
        rpc.assert_not_called()
