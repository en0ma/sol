"""Six-venue orchestration: offline-only, exact scoped venues, no fake profit."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from arb.six_venue_pipeline import VENUES,authenticated_graph,source_research,offline_research,assess_signed_batch,preflight_candidate_cycles_against_registry,report_signed_source_cycle_preflight


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

    def test_existing_source_graph_feeds_provenance_preflight_without_route_approval(self):
        accepted={"venue":"pumpswap","address":"P1","mints":["A","B"],
            "signed_provenance":{"status":"INDEPENDENT_SIGNED_NATIVE_SDK_SPL_PARITY",
                "source_slot":100,"source_digest":"a"*64,
                "independent_receipt_sha256":"b"*64,
                "signed_transaction_hashes":[str(i)*64 for i in range(4)]}}
        other={"venue":"meteora_dlmm","address":"P2","mints":["B","A"],
            "signed_provenance":{"status":"INDEPENDENT_DLMM_SIGNED_NATIVE_SDK_SPL_PARITY",
                "source_slot":100,"source_digest":"a"*64,
                "independent_receipt_sha256":"b"*64,
                "signed_transaction_hashes":[str(i)*64 for i in range(4)]}}
        source=readiness()
        source["authenticated_pools"]["pumpswap"]=[{
            "venue":"pumpswap","pool":"P1","slot":101,"mints":["A","B"],
            "authenticated":True,"actionable":False,"broadcast":False,
            "live_execution_approved":False}]
        source["authenticated_pools"]["meteora_dlmm"]=[{
            "venue":"meteora_dlmm","pool":"P2","slot":101,"mints":["B","A"],
            "authenticated":True,"actionable":False,"broadcast":False,
            "live_execution_approved":False}]
        graph=authenticated_graph(source)
        report=report_signed_source_cycle_preflight(
            {"pools":[accepted,other]},source,graph)
        tampered={**graph,"routes":[{**graph["routes"][0],
            "legs":[{**graph["routes"][0]["legs"][0],"pool":"FORGED"},
                    *graph["routes"][0]["legs"][1:]]},*graph["routes"][1:]]}
        with self.assertRaisesRegex(ValueError,"not bound"):
            report_signed_source_cycle_preflight(
                {"pools":[accepted,other]},source,tampered)
        self.assertGreater(report["source_identity_routes"],0)
        self.assertEqual(report["coordinator_eligible_routes"],0)
        self.assertFalse(report["actionable"])
        altered=readiness()
        altered["authenticated_pools"]["pumpswap"]=[{
            **source["authenticated_pools"]["pumpswap"][0],"mints":["A","X"]}]
        with self.assertRaisesRegex(ValueError,"not bound|disagree"):
            report_signed_source_cycle_preflight({"pools":[accepted]},altered,graph)

    def test_no_mainnet_rpc_or_implicit_offline_approval(self):
        with self.assertRaises((ValueError,OSError)):
            source_research("https://api.mainnet-beta.solana.com",{},
                            "/tmp/a",amount_in=100,observed_unix=1000)
        with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"0"}):
            with self.assertRaisesRegex(ValueError,"opt-in"):
                offline_research("http://127.0.0.1:8899","/tmp/a","/tmp/b")

    def test_source_backed_quote_handoff_and_offline_simulation(self):
        fixture={"route_venues":["orca","raydium_cpmm","pumpswap"],
                 "route_mints":["a","b","c","a"],
                 "route_pool_addresses":["p1","p2","p3"],
                 "state_accounts_observed_slot":123}
        ranked={"status":"GROSS_SOURCE_BOUND_RANKING_ONLY",
                "fully_quoted":2,"blocked":0,"positive_gross":1,
                "ranked":[{"index":0,"positive_gross":True,"actionable":False},
                          {"index":1,"positive_gross":False,"actionable":False}]}
        signed={"attempted":1,"independent_signed_accepted":1,
                "observed_venue_quote_exact_matches":3,
                "routes":[{"index":7,"independent_signed_accepted":True,
                           "economics_status":"COST_EVIDENCE_BLOCKED",
                           "actionable":False,"broadcast":False}]}
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/"source"
            dst=Path(temp)/"signed"
            def export(_rpc,_readiness,folder,*,maximum):
                folder.mkdir()
                (folder/"triangle-00.json").write_text(json.dumps(fixture))
                (folder/"triangle-01.json").write_text(json.dumps(fixture))
                summary={"exported":2,"routes":[
                    {"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE",
                     "index":7,"fixture":"triangle-00.json"},
                    {"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE",
                     "index":9,"fixture":"triangle-01.json"}]}
                (folder/"summary.json").write_text(json.dumps(summary))
                return summary
            with patch("arb.six_venue_pipeline.probe",return_value=readiness()) as pm, \
                 patch("arb.m5_distinct_venue_coverage_batch.source_batch",side_effect=export), \
                 patch("arb.m5_source_triangle_quote_ranking.rank",return_value=ranked):
                result=source_research("http://127.0.0.1:8899",
                    {"pools":[]},src,amount_in=1000,observed_unix=1000)
            self.assertEqual(len(pm.call_args.kwargs["batch"]),30)
            self.assertEqual(result["manifest"]["selected_source_route_indices"],[7])
            self.assertEqual(result["quote"]["net_profitable_confirmed"],0)
            with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}), \
                 patch("arb.m5_distinct_venue_coverage_batch.offline_batch",return_value=signed) as offline:
                report=offline_research("http://127.0.0.1:8899",src,dst)
            self.assertEqual(offline.call_args.kwargs["route_indices"],[7])
            self.assertEqual(report["independent_signed_accepted"],1)
            self.assertEqual(report["route_decisions"]["signed_accepted"],1)
            self.assertEqual(report["route_decisions"]["net_profitable_candidates"],0)
            self.assertFalse(report["actionable"])
            self.assertFalse(report["broadcast"])
            (src/"six-venue-ranking.json").write_text('{"tampered":true}')
            with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
                with self.assertRaisesRegex(ValueError,"ranking digest"):
                    offline_research("http://127.0.0.1:8899",src,dst)
            (src/"six-venue-ranking.json").write_text(json.dumps(ranked,
                sort_keys=True,separators=(",",":")))
            original_summary=(src/"summary.json").read_text()
            (src/"summary.json").write_text('{"routes":[]}')
            with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
                with self.assertRaisesRegex(ValueError,"inventory"):
                    offline_research("http://127.0.0.1:8899",src,dst)
            (src/"summary.json").write_text(original_summary)
            preflight_path=src/"six-venue-source-cycle-preflight.json"
            frozen_preflight=preflight_path.read_bytes()
            preflight_path.write_text('{"forged":true}')
            with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
                with self.assertRaisesRegex(ValueError,"source cycle preflight digest"):
                    offline_research("http://127.0.0.1:8899",src,dst)
            preflight_path.write_bytes(frozen_preflight)
            manifest_path=src/"six-venue-handoff.json"
            original_manifest=manifest_path.read_text()
            unsafe=json.loads(frozen_preflight)
            unsafe["coordinator_eligible_routes"]=1
            preflight_path.write_text(json.dumps(unsafe))
            manifest=json.loads(original_manifest)
            import hashlib
            manifest["source_cycle_preflight_sha256"]=hashlib.sha256(
                preflight_path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest))
            with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
                with self.assertRaisesRegex(ValueError,"not fail-closed"):
                    offline_research("http://127.0.0.1:8899",src,dst)
            preflight_path.write_bytes(frozen_preflight)
            manifest_path.write_text(original_manifest)
            (src/"triangle-00.json").write_text('{"tampered":true}')
            with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
                with self.assertRaisesRegex(ValueError,"digest"):
                    offline_research("http://127.0.0.1:8899",src,dst)

    def test_signed_ledger_rejects_missing_or_false_acceptance(self):
        row={"index":3,"independent_signed_accepted":True,
             "actionable":False,"broadcast":False}
        batch={"attempted":1,"independent_signed_accepted":1,"routes":[row]}
        self.assertEqual(assess_signed_batch(batch,[3])["signed_accepted"],1)
        with self.assertRaisesRegex(ValueError,"inconsistent"):
            assess_signed_batch(batch,[4])
        with self.assertRaisesRegex(ValueError,"inconsistent"):
            assess_signed_batch({**batch,"independent_signed_accepted":0},[3])
        with self.assertRaisesRegex(ValueError,"inconsistent"):
            assess_signed_batch({**batch,"routes":[{**row,"actionable":True}]},[3])

    def test_signed_economics_rejects_inconsistent_integer_evidence(self):
        base={"index":1,"independent_signed_accepted":True,
              "actionable":False,"broadcast":False,
              "gross_start_mint_delta":1200,
              "break_even_total_cost_budget_start_mint_base_units":1200,
              "observed_compute_units":100000}
        def batch(row):
            return {"attempted":1,"independent_signed_accepted":1,"routes":[row]}
        valid=assess_signed_batch(batch(base),[1])
        self.assertEqual(valid["gross_ranked_signed_research"][0][
            "maximum_affordable_total_cost_start_mint_base_units"],1200)
        for changes in (
            {"gross_start_mint_delta":1200.5},
            {"gross_start_mint_delta":True},
            {"break_even_total_cost_budget_start_mint_base_units":1201},
            {"break_even_total_cost_budget_start_mint_base_units":-1},
            {"observed_compute_units":0},
            {"observed_compute_units":1400001},
            {"observed_compute_units":True}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError,"signed gross"):
                    assess_signed_batch(batch({**base,**changes}),[1])

    def test_registry_to_two_leg_source_preflight_not_coordinator_admission(self):
        status="INDEPENDENT_SIGNED_NATIVE_SDK_SPL_PARITY"
        pools=[]
        source=[]
        for i,(venue,mints,proof_status) in enumerate((
            ("pumpswap",["A","B"],status),
            ("meteora_dlmm",["B","A"],"INDEPENDENT_DLMM_SIGNED_NATIVE_SDK_SPL_PARITY"))):
            pools.append({"venue":venue,"address":f"P{i}","mints":mints,
                          "signed_provenance":{"status":proof_status,
                              "source_slot":123,"source_digest":"a"*64,
                              "independent_receipt_sha256":"b"*64,
                              "signed_transaction_hashes":[str(j)*64 for j in range(4)]}})
            source.append({"venue":venue,"address":f"P{i}","mints":mints,
                           "current_source_slot":124,"source_identity_refreshed":True,
                           "current_complete_fee_and_tick_state_verified":False,
                           "current_native_sdk_signed_quote_verified":False,
                           "coordinator_eligible":False})
        fresh={"status":"FRESH_IDENTITY_ONLY_NOT_USABLE_REGISTRY_ADMISSION",
               "source_authenticated":source,"coordinator_eligible_count":0,
               "actionable":False,"live_execution_approved":False,"broadcast":False}
        legs=[{"venue":p["venue"],"pool":p["address"],
               "input_mint":p["mints"][0],"output_mint":p["mints"][1]} for p in pools]
        routes=[{"legs":legs,"tokens":["A","B","A"]},
                {"legs":[{**legs[0],"pool":"unsigned"},legs[1]],"tokens":["A","B","A"]},
                {"legs":legs}]
        report=preflight_candidate_cycles_against_registry({"pools":pools},fresh,routes)
        self.assertEqual(report["source_identity_routes"],1)
        self.assertEqual(report["blocked_routes"],2)
        self.assertEqual(report["coordinator_eligible_routes"],0)
        self.assertFalse(report["actionable"])

    def test_gross_loss_quoted_route_is_diagnostic_only(self):
        quote={"status":"GROSS_SOURCE_BOUND_RANKING_ONLY",
               "fully_quoted":1,"blocked":0,"positive_gross":0,
               "ranked":[{"index":0,"positive_gross":False,
                          "actionable":False}]}
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/"source"
            dst=Path(temp)/"signed"
            def export(_rpc,_readiness,folder,*,maximum):
                folder.mkdir()
                (folder/"triangle.json").write_text(json.dumps({
                    "route_venues":["orca","raydium_cpmm","raydium_clmm"]}))
                summary={"exported":1,"routes":[{
                    "index":4,"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE",
                    "fixture":"triangle.json"}]}
                (folder/"summary.json").write_text(json.dumps(summary))
                return summary
            with patch("arb.six_venue_pipeline.probe",return_value=readiness()), \
                 patch("arb.m5_distinct_venue_coverage_batch.source_batch",side_effect=export), \
                 patch("arb.m5_source_triangle_quote_ranking.rank",return_value=quote):
                report=source_research("http://127.0.0.1:8899",
                    {"pools":[]},src,amount_in=100,observed_unix=100)
            self.assertEqual(report["manifest"]["diagnostic_only_indices"],[4])
            self.assertEqual(report["manifest"]["positive_gross_indices"],[])
            signed={"attempted":1,"independent_signed_accepted":0,
                    "routes":[{"index":4,"independent_signed_accepted":False,
                              "actionable":False,"broadcast":False}]}
            with patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}), \
                 patch("arb.m5_distinct_venue_coverage_batch.offline_batch",return_value=signed):
                offline=offline_research("http://127.0.0.1:8899",src,dst)
            self.assertEqual(offline["diagnostic_only_signed_routes"],1)
            self.assertEqual(offline["selected_positive_gross_routes"],0)
            self.assertEqual(offline["independent_signed_accepted"],0)
            self.assertEqual(offline["net_profitable_confirmed"],0)

    def test_new_onchain_discovery_hints_must_reauthenticate(self):
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/"source"
            addr="new-from-original-onchain-lookup"
            discovered={"status":"PARTIAL","candidate_graph_verified_count":1,
                        "candidate_graph_pool_identities":[
                            {"venue":"orca","address":addr,
                             "mints":["a","b"],"slot":300}],
                        "errors":[{"reason":"unavailable other venue"}]}
            observed={}
            def source_probe(_rpc, registry, *, batch):
                observed["registry"]=registry
                return readiness()
            def export(_rpc,_readiness,folder,*,maximum):
                folder.mkdir()
                data={"exported":0,"routes":[]}
                (folder/"summary.json").write_text(json.dumps(data))
                return data
            rank_empty={"status":"GROSS_SOURCE_BOUND_RANKING_ONLY","fully_quoted":0,"blocked":0,"positive_gross":0,
                        "ranked":[]}
            with patch("arb.onchain_pool_discovery.discover",return_value=discovered) as d, \
                 patch("arb.six_venue_pipeline.probe",side_effect=source_probe), \
                 patch("arb.m5_distinct_venue_coverage_batch.source_batch",side_effect=export), \
                 patch("arb.m5_source_triangle_quote_ranking.rank",return_value=rank_empty):
                report=source_research("http://127.0.0.1:8899",
                    {"pools":[]},src,amount_in=100,observed_unix=100,
                    discovery_pairs=[["mintA","mintB"]])
            self.assertEqual(observed["registry"]["pools"][0]["address"],addr)
            self.assertEqual(d.call_args.kwargs["venues"],VENUES)
            self.assertEqual(report["discovery"]["venue_owned_search"]["new_identity_hints"],1)
            self.assertEqual(report["quote"]["net_profitable_confirmed"],0)
            with self.assertRaisesRegex(ValueError,"discovery mint pairs"):
                source_research("http://127.0.0.1:8899",{"pools":[]},src,
                     amount_in=100,observed_unix=100,discovery_pairs=[["a","a"]])

    def test_rejects_out_of_scope_source_fixture(self):
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/"source"
            def export(_rpc,_readiness,folder,*,maximum):
                folder.mkdir()
                (folder/"fixture.json").write_text(json.dumps(
                    {"route_venues":["orca","meteora_dbc","pumpswap"]}))
                return {"exported":1,"routes":[{
                    "status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE",
                    "index":0,"fixture":"fixture.json"}]}
            with patch("arb.six_venue_pipeline.probe",return_value=readiness()), \
                 patch("arb.m5_distinct_venue_coverage_batch.source_batch",side_effect=export):
                with self.assertRaisesRegex(ValueError,"out-of-scope"):
                    source_research("http://127.0.0.1:8899",{"pools":[]},
                                    src,amount_in=10,observed_unix=100)


if __name__=="__main__":
    unittest.main()
