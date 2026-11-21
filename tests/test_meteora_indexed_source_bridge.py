"""Meteora indexed hints never establish source pools, topology or execution."""
import base64
import unittest
from unittest.mock import patch
from arb.meteora_indexed_source_bridge import discover,indexed_addresses,audit_recent_pools_isolated
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

    def test_second_venue_prioritizes_triangle_closed_by_first_verified_venue(self):
        damm="meteora_damm_v2"
        dlmm="meteora_dlmm"
        first="Y"*32
        final="Z"*32
        decoy="A"*32
        base=[{"venue":"orca","address":"ab","mints":["A","B"]}]
        found={damm:[first],dlmm:[decoy,final]}
        tokens={
            first:("B","C"),
            final:("C","A"),
            decoy:("X","Y"),
        }
        def index(venue,**kwargs):
            return [{"venue":venue,"address":address}
                    for address in found[venue]]
        def read(rpc,method,params):
            self.assertEqual(method,"getMultipleAccounts")
            return {"value":[{"owner":PROGRAMS[damm] if addr==first
                    else PROGRAMS[dlmm],"executable":False,
                    "data":[base64.b64encode(addr.encode()).decode(),"base64"]}
                    for addr in params[0]]}
        checks=[]
        def verify(rpc,venue,address,state):
            checks.append(address)
            return {"venue":venue,"address":address,
                    "mints":list(tokens[address]),"slot":99,
                    "swap_simulated":False}
        with patch("arb.meteora_indexed_source_bridge.local_rpc_only"),patch.dict(
                "arb.meteora_indexed_source_bridge.DECODERS",{
                    damm:lambda raw:{"token_a_mint":tokens[raw.decode()][0],
                                     "token_b_mint":tokens[raw.decode()][1]},
                    dlmm:lambda raw:{"token_x_mint":tokens[raw.decode()][0],
                                     "token_y_mint":tokens[raw.decode()][1]}}):
            report=discover(RPC,base,venues=(damm,dlmm),
                maximum_verify_per_venue=1,index_fn=index,
                call_fn=read,verify_fn=verify)
        self.assertEqual(checks,[first,final])
        self.assertEqual(report["verified_new_pool_count"],2)
        self.assertEqual(report["additional_topology_start_mints"],
                         ["A","B","C"])
        self.assertEqual(report["venue_reports"][dlmm][
            "ranking_prior_verified_venue_pools"],1)
        self.assertFalse(report["actionable"])
        self.assertFalse(report["signed_simulation_verified"])

    def test_four_page_bounded_index_discovery(self):
        import io,json
        class Response(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        calls=[]
        def pages(req,timeout):
            from urllib.parse import urlsplit,parse_qs
            params=parse_qs(urlsplit(req.full_url).query)
            page=int(params["page"][0])
            calls.append(page)
            return Response(json.dumps({"data":[{"address":str(page)*32}],
                "current_page":page,"pages":4}).encode())
        with patch("arb.meteora_indexed_source_bridge.urlopen",
                   side_effect=pages):
            hints=indexed_addresses(VENUE,pages=4,page_size=1)
        self.assertEqual(calls,[1,2,3,4])
        self.assertEqual(len(hints),4)

    def test_two_sort_orders_deduplicate_and_reach_newer_pools(self):
        import io,json
        from urllib.parse import urlsplit,parse_qs
        class Response(io.BytesIO):
            def __enter__(self):return self
            def __exit__(self,*args):self.close()
        calls=[]
        def index(req,timeout):
            qs=parse_qs(urlsplit(req.full_url).query)
            order=qs["sort_by"][0]
            page=int(qs["page"][0])
            calls.append((order,page))
            addresses={
                ("tvl:desc",1):["A"*32,"B"*32],
                ("tvl:desc",2):["B"*32,"C"*32],
                ("pool_created_at:desc",1):["C"*32,"D"*32],
                ("pool_created_at:desc",2):["E"*32,"A"*32],
            }[(order,page)]
            return Response(json.dumps({"data":[{"address":a} for a in addresses],
                "current_page":page,"pages":2}).encode())
        with patch("arb.meteora_indexed_source_bridge.urlopen",
                   side_effect=index):
            hints=indexed_addresses(VENUE,pages=2,page_size=2,
                sort_orders=("tvl:desc","pool_created_at:desc"))
        self.assertEqual([h["address"] for h in hints],
                         ["A"*32,"B"*32,"C"*32,"D"*32,"E"*32])
        self.assertEqual(calls,[
            ("tvl:desc",1),("tvl:desc",2),
            ("pool_created_at:desc",1),("pool_created_at:desc",2)])

    def test_multiple_sort_index_limits_fail_closed(self):
        with patch("arb.meteora_indexed_source_bridge.local_rpc_only"):
            for sorts in (("tvl:desc","tvl:desc"),("unapproved:desc",),
                          ("tvl:desc",)*4):
                with self.assertRaises(ValueError):
                    discover(RPC,[],sort_orders=sorts)
            with self.assertRaises(ValueError):
                discover(RPC,[],pages=5,
                    sort_orders=("tvl:desc","pool_created_at:desc"))

    def test_recent_pool_audit_never_admits_into_control_graph(self):
        baseline=[{"venue":"orca","address":"ab","mints":["A","B"]},
                  {"venue":"meteora_damm_v2","address":"bc",
                   "mints":["B","C"]}]
        original=[dict(x) for x in baseline]
        def scout(rpc,entries,**kwargs):
            self.assertEqual(kwargs["sort_orders"],
                             ("pool_created_at:desc",))
            self.assertEqual(kwargs["maximum_verify_per_venue"],12)
            return {"status":"READ_ONLY_METEORA_INDEXED_SOURCE_SCOUT",
                    "venue_reports":{VENUE:{"verified_pools":1}},
                    "source_verified_new_pools":[{
                        "venue":VENUE,"address":"new",
                        "mints":["C","A"],
                        "source_verified_slot":42,
                        "source_verified_only":True}],
                    "signed_simulation_verified":False,
                    "actionable":False,"broadcast":False}
        report=audit_recent_pools_isolated(
            RPC,baseline,discover_fn=scout)
        self.assertEqual(report["incremental_topology_start_mints"],3)
        self.assertEqual(report["source_verified_recent_pools"],1)
        self.assertFalse(report["admitted_to_primary_graph"])
        self.assertNotIn("source_verified_new_pools",report)
        self.assertEqual(baseline,original)
        self.assertFalse(report["signed_simulation_verified"])

    def test_recent_audit_rejects_unverified_evidence(self):
        def bad(rpc,entries,**kwargs):
            return {"status":"READ_ONLY_METEORA_INDEXED_SOURCE_SCOUT",
                    "source_verified_new_pools":[],
                    "signed_simulation_verified":True,
                    "actionable":False,"broadcast":False}
        with self.assertRaisesRegex(ValueError,"invalid isolated"):
            audit_recent_pools_isolated(RPC,[],discover_fn=bad)

    def test_invalid_bounds_fail_closed(self):
        with patch("arb.meteora_indexed_source_bridge.local_rpc_only"):
            with self.assertRaises(ValueError):
                discover(RPC,[],maximum_verify_per_venue=0)
            with self.assertRaises(ValueError):
                discover(RPC,[],venues=("meteora_dlmm","meteora_dlmm"))

if __name__=="__main__":
    unittest.main()
