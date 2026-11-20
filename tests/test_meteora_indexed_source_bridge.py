"""Meteora indexed hints never establish source pools, topology or execution."""
import base64
import unittest
from unittest.mock import patch
from arb.meteora_indexed_source_bridge import discover,indexed_addresses
from arb.next_ten_fork_pool_probe import PROGRAMS

RPC="http://127.0.0.1:8899"
VENUE="meteora_damm_v2"

class MeteoraIndexerTests(unittest.TestCase):
    def test_official_index_pages_are_address_only_hints(self):
        import io,json
        from unittest.mock import patch
        from urllib.parse import urlsplit,parse_qs
        class Response(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        visited=[]
        def fake_open(req,timeout):
            parsed=urlsplit(req.full_url)
            query=parse_qs(parsed.query)
            visited.append((parsed.hostname,query["page"][0]))
            page=int(query["page"][0])
            return Response(json.dumps({"data":[{"address":str(page)*32}],
                "current_page":page,"pages":2}).encode())
        with patch("arb.meteora_indexed_source_bridge.urlopen",
                   side_effect=fake_open):
            hints=indexed_addresses(VENUE,pages=2,page_size=1)
        self.assertEqual(len(hints),2)
        self.assertEqual(visited,[("damm-v2.datapi.meteora.ag","1"),
                                  ("damm-v2.datapi.meteora.ag","2")])

    def test_source_reverified_missing_triangle_only(self):
        base=[{"venue":"orca","address":"ab","mints":["A","B"]},
              {"venue":"raydium_cpmm","address":"bc","mints":["B","C"]}]
        addr="Q"*32
        raw=base64.b64encode(addr.encode()).decode()
        def read(rpc,method,params):
            self.assertEqual(method,"getMultipleAccounts")
            return {"value":[{"owner":PROGRAMS[VENUE],"executable":False,
                              "data":[raw,"base64"]}]}
        calls=[]
        def verify(rpc,venue,address,state):
            calls.append(address)
            return {"venue":venue,"address":address,"mints":["C","A"],
                    "slot":42,"swap_simulated":False}
        with patch("arb.meteora_indexed_source_bridge.local_rpc_only"),patch.dict(
                "arb.meteora_indexed_source_bridge.DECODERS",{
                    VENUE:lambda raw:{"token_a_mint":"C","token_b_mint":"A"}}):
            report=discover(RPC,base,venues=(VENUE,),
                index_fn=lambda venue,**kwargs:[
                    {"venue":venue,"address":addr}],
                call_fn=read,verify_fn=verify)
        self.assertEqual(calls,[addr])
        self.assertEqual(report["verified_new_pool_count"],1)
        self.assertEqual(report["additional_topology_start_mints"],
                         ["A","B","C"])
        self.assertFalse(report["broadcast"])
        self.assertFalse(report["signed_simulation_verified"])

    def test_unauthenticated_liquidity_cannot_enter_topology(self):
        base=[{"venue":"orca","address":"ab","mints":["A","B"]},
              {"venue":"raydium_cpmm","address":"bc","mints":["B","C"]}]
        addr="Q"*32
        raw=base64.b64encode(addr.encode()).decode()
        with patch("arb.meteora_indexed_source_bridge.local_rpc_only"),patch.dict(
                "arb.meteora_indexed_source_bridge.DECODERS",{
                    VENUE:lambda raw:{"token_a_mint":"C","token_b_mint":"A"}}):
            report=discover(RPC,base,venues=(VENUE,),
                index_fn=lambda venue,**kwargs:[
                    {"venue":venue,"address":addr}],
                call_fn=lambda *_:{"value":[{"owner":PROGRAMS[VENUE],
                    "executable":False,"data":[raw,"base64"]}]},
                verify_fn=lambda *_:{"venue":VENUE,"address":addr,
                    "mints":["WRONG","A"],"slot":42,"swap_simulated":False})
        self.assertEqual(report["verified_new_pool_count"],0)
        self.assertEqual(report["additional_topology_start_mints"],[])

    def test_indexer_outage_does_not_claim_verified_pool(self):
        with patch("arb.meteora_indexed_source_bridge.local_rpc_only"):
            result=discover(RPC,[],venues=(VENUE,),index_fn=lambda *a,**kw:
                (_ for _ in ()).throw(OSError("secret API URL")))
        self.assertEqual(result["venue_reports"][VENUE]["status"],
                         "INDEXER_UNAVAILABLE")
        self.assertNotIn("secret",str(result))
        self.assertEqual(result["verified_new_pool_count"],0)

    def test_invalid_bounds_fail_closed(self):
        with patch("arb.meteora_indexed_source_bridge.local_rpc_only"):
            with self.assertRaises(ValueError):
                discover(RPC,[],maximum_verify_per_venue=0)
            with self.assertRaises(ValueError):
                discover(RPC,[],venues=("meteora_dlmm","meteora_dlmm"))

if __name__=="__main__":
    unittest.main()
