"""Indexer addresses never become authenticated topology without source reads."""
import base64
import unittest
from unittest.mock import patch
from arb.raydium_indexer_source_bridge import discover
from arb.raydium_cpmm import PROGRAM

RPC="http://127.0.0.1:8899"
def pool(venue,address,a,b):
    return {"venue":venue,"address":address,"mints":[a,b]}

def indexer(*,pages,page_size):
    return [{"venue":"raydium_cpmm","address":"A"*32},
            {"venue":"raydium_cpmm","address":"B"*32}]

class IndexedBridgeTests(unittest.TestCase):
    def test_source_verified_new_connection_only_and_no_profit_claim(self):
        base=[pool("orca","first","A","B"),
              pool("meteora_damm_v2","second","B","C")]
        raw=base64.b64encode(b"fake-state").decode()
        def fetch(rpc,method,params):
            self.assertEqual(method,"getMultipleAccounts")
            self.assertEqual(len(params[0]),2)
            return {"value":[{"owner":PROGRAM,"executable":False,
                              "data":[raw,"base64"]},
                             {"owner":"untrusted","executable":False,
                              "data":[raw,"base64"]}]}
        def authenticate(rpc,venue,address,state):
            self.assertEqual(address,"A"*32)
            return {"venue":venue,"address":address,"mints":["A","C"],
                    "slot":120,"swap_simulated":False}
        with patch("arb.raydium_indexer_source_bridge.local_rpc_only"),patch(
                "arb.raydium_indexer_source_bridge.decode",
                return_value={"token_0_mint":"A","token_1_mint":"C"}):
            report=discover(RPC,base,index_fn=indexer,
                            call_fn=fetch,verify_fn=authenticate)
        self.assertEqual(report["verified_new_pool_count"],1)
        self.assertEqual(report["additional_topology_start_mints"],["A","B","C"])
        self.assertEqual(report["invalid_source_account_count"],1)
        self.assertTrue(report["indexer_is_not_source_evidence"])
        self.assertFalse(report["actionable"])
        self.assertFalse(report["signed_simulation_verified"])

    def test_unverified_and_mismatched_source_fails_closed(self):
        raw=base64.b64encode(b"x").decode()
        def fetch(*args):
            return {"value":[{"owner":PROGRAM,"executable":False,
                              "data":[raw,"base64"]} for _ in range(2)]}
        with patch("arb.raydium_indexer_source_bridge.local_rpc_only"),patch(
                "arb.raydium_indexer_source_bridge.decode",
                return_value={"token_0_mint":"A","token_1_mint":"C"}):
            report=discover(RPC,[],index_fn=indexer,call_fn=fetch,
                            verify_fn=lambda rpc,venue,address,state:{
                                "venue":venue,"address":address,
                                "mints":["WRONG","C"],"slot":120,
                                "swap_simulated":False})
        self.assertEqual(report["verified_new_pool_count"],0)
        self.assertEqual(report["source_verification_failures"],2)

    def test_indexer_failure_is_explicit_and_does_not_abort_source_ci(self):
        def unavailable(**kwargs):
            raise OSError("HTTP 429 https://private-provider.example/key=SECRET")
        with patch("arb.raydium_indexer_source_bridge.local_rpc_only"):
            report=discover(RPC,[],index_fn=unavailable)
        self.assertEqual(report["status"],"UNTRUSTED_INDEXER_UNAVAILABLE")
        self.assertEqual(report["verified_new_pool_count"],0)
        self.assertNotIn("SECRET",str(report))

    def test_indexer_cannot_invent_many_pool_addresses(self):
        with patch("arb.raydium_indexer_source_bridge.local_rpc_only"):
            with self.assertRaisesRegex(ValueError,"unbounded"):
                discover(RPC,[],pages=1,page_size=1,
                         index_fn=lambda **kwargs:indexer(**kwargs))
            with self.assertRaisesRegex(ValueError,"invalid bounded"):
                discover(RPC,[],pages=0,index_fn=indexer)

if __name__=="__main__":
    unittest.main()
