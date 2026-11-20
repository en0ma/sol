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

    def test_complementary_missing_edges_beat_alphabetical_decoys(self):
        # Neither New-B nor New-C forms a triangle in isolation; together
        # they close New-B-C-New using the existing B-C pool. The old
        # direct-gain-only ranking would spend both verify slots on decoys.
        existing=[pool("orca","bc","B","C")]
        ordered=[("A"*32,"X","Y"),("B"*32,"P","Q"),
                 ("Y"*32,"New","B"),("Z"*32,"New","C")]
        source_by_address={addr:(a,b) for addr,a,b in ordered}
        index_rows=[{"venue":"raydium_cpmm","address":addr}
                    for addr,_,_ in ordered]
        def read(rpc,method,params):
            return {"value":[{"owner":PROGRAM,"executable":False,
                "data":[base64.b64encode(addr.encode()).decode(),"base64"]}
                for addr in params[0]]}
        checked=[]
        def reverify(rpc,venue,address,state):
            checked.append(address)
            return {"venue":venue,"address":address,
                    "mints":[state["token_0_mint"],state["token_1_mint"]],
                    "slot":123,"swap_simulated":False}
        with patch("arb.raydium_indexer_source_bridge.local_rpc_only"),patch(
                "arb.raydium_indexer_source_bridge.decode",
                side_effect=lambda raw:dict(zip(
                    ("token_0_mint","token_1_mint"),
                    source_by_address[raw.decode()]))):
            result=discover(RPC,existing,maximum_verify=2,
                index_fn=lambda **kwargs:index_rows,
                call_fn=read,verify_fn=reverify)
        self.assertEqual(checked,["Y"*32,"Z"*32])
        self.assertEqual(result["complementary_edge_candidates"],2)
        self.assertEqual(result["additional_topology_start_mints"],
                         ["B","C","New"])
        self.assertEqual(result["verified_new_pool_count"],2)
        self.assertFalse(result["signed_simulation_verified"])
        self.assertFalse(result["broadcast"])

    def test_complementary_unverified_pool_does_not_create_topology(self):
        existing=[pool("orca","bc","B","C")]
        rows=[{"venue":"raydium_cpmm","address":"Y"*32},
              {"venue":"raydium_cpmm","address":"Z"*32}]
        def read(rpc,method,params):
            return {"value":[{"owner":PROGRAM,"executable":False,
                "data":[base64.b64encode(addr.encode()).decode(),"base64"]}
                for addr in params[0]]}
        with patch("arb.raydium_indexer_source_bridge.local_rpc_only"),patch(
                "arb.raydium_indexer_source_bridge.decode",
                side_effect=lambda raw:{"token_0_mint":"New",
                    "token_1_mint":"B" if raw.decode()=="Y"*32 else "C"}):
            result=discover(RPC,existing,maximum_verify=2,
                index_fn=lambda **kwargs:rows,call_fn=read,
                verify_fn=lambda rpc,venue,address,state:
                    (_ for _ in ()).throw(ValueError("vault inaccessible")))
        self.assertEqual(result["complementary_edge_candidates"],2)
        self.assertEqual(result["verified_new_pool_count"],0)
        self.assertEqual(result["additional_topology_start_mints"],[])
        self.assertEqual(result["source_verification_failures"],2)

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
