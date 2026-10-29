"""Six-venue orchestration: offline-only, exact scoped venues, no fake profit."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from arb.six_venue_pipeline import VENUES,authenticated_graph,research


def readiness():
    pools={v:[] for v in VENUES}
    pools["orca"]=[{"venue":"orca","pool":"pool1","slot":123,
                    "mints":["mintA","mintB"],"authenticated":True,
                    "actionable":False,"broadcast":False,
                    "live_execution_approved":False}]
    return {"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
            "authenticated_pools":pools,"failed_pool_checks":[],
            "actionable":False,"broadcast":False,
            "live_execution_approved":False}


class SixVenuePipelineTests(unittest.TestCase):
    def test_authenticated_graph_requires_exact_six_no_dbc_or_amm4(self):
        x=authenticated_graph(readiness())
        self.assertEqual(x["source_pool_count"],1)
        self.assertEqual(set(x["venues"]),set(VENUES))
        self.assertEqual(x["candidate_cycles"],0)
        self.assertFalse(x["actionable"])
        wrong=readiness()
        wrong["authenticated_pools"]["meteora_dbc"]=[]
        with self.assertRaisesRegex(ValueError,"six authenticated venues"):
            authenticated_graph(wrong)
        wrong=readiness()
        wrong["authenticated_pools"]["orca"][0]["authenticated"]=False
        with self.assertRaisesRegex(ValueError,"untrusted"):
            authenticated_graph(wrong)

    def test_no_mainnet_rpc_or_implicit_offline_approval(self):
        with self.assertRaises((ValueError,OSError)):
            research("https://api.mainnet-beta.solana.com",{}, "/tmp/a",
                     "/tmp/b",amount_in=100,observed_unix=1000)
        with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"0"}):
            with self.assertRaisesRegex(ValueError,"opt-in"):
                research("http://127.0.0.1:8899",{},"/tmp/a","/tmp/b",
                         amount_in=100,observed_unix=1000)

    def test_integrated_quote_rank_to_signed_selection(self):
        fixture={"route_venues":["orca","raydium_cpmm","pumpswap"],
                 "route_mints":["a","b","c","a"],
                 "route_pool_addresses":["p1","p2","p3"],
                 "state_accounts_observed_slot":123}
        report={"status":"GROSS_SOURCE_BOUND_RANKING_ONLY",
                "fully_quoted":2,"blocked":1,"positive_gross":1,
                "ranked":[{"index":0,"positive_gross":True},
                          {"index":1,"positive_gross":False}],
                "actionable":False,"broadcast":False}
        signed={"attempted":1,"independent_signed_accepted":1,
                "observed_venue_quote_exact_matches":3}
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/"source"
            dst=Path(temp)/"signed"
            def export(_rpc,_readiness,folder,*,maximum):
                folder.mkdir()
                (folder/"triangle-00.json").write_text(json.dumps(fixture))
                (folder/"triangle-01.json").write_text(json.dumps(fixture))
                return {"exported":2,"routes":[
                    {"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE",
                     "index":7,"fixture":"triangle-00.json"},
                    {"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE",
                     "index":9,"fixture":"triangle-01.json"}]}
            with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}), \
                 patch("arb.six_venue_pipeline.probe",return_value=readiness()) as probe_mock, \
                 patch("arb.m5_distinct_venue_coverage_batch.source_batch",side_effect=export), \
                 patch("arb.m5_source_triangle_quote_ranking.rank",return_value=report), \
                 patch("arb.m5_distinct_venue_coverage_batch.offline_batch",return_value=signed) as offline:
                result=research("http://127.0.0.1:8899",{"pools":[]},
                                src,dst,amount_in=1000,observed_unix=1000)
            self.assertEqual(len(probe_mock.call_args.kwargs["batch"]),30)
            self.assertEqual(offline.call_args.kwargs["route_indices"],[7])
            self.assertEqual(result["simulation"]["independent_signed_accepted"],1)
            self.assertEqual(result["quote"]["net_profitable_confirmed"],0)
            self.assertFalse(result["actionable"])
            self.assertFalse(result["broadcast"])

    def test_rejects_out_of_scope_source_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/"source"
            dst=Path(temp)/"signed"
            def export(_rpc,_readiness,folder,*,maximum):
                folder.mkdir()
                (folder/"fixture.json").write_text(json.dumps(
                    {"route_venues":["orca","meteora_dbc","pumpswap"]}))
                return {"exported":1,"routes":[{
                    "status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE",
                    "index":0,"fixture":"fixture.json"}]}
            with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}), \
                 patch("arb.six_venue_pipeline.probe",return_value=readiness()), \
                 patch("arb.m5_distinct_venue_coverage_batch.source_batch",side_effect=export):
                with self.assertRaisesRegex(ValueError,"out-of-scope"):
                    research("http://127.0.0.1:8899",{"pools":[]},
                             src,dst,amount_in=10,observed_unix=100)


if __name__=="__main__":
    unittest.main()
