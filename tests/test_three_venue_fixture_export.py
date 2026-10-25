import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from arb.next_ten_pair_fixture_export import export_three_venue
from arb.next_ten_fork_pool_probe import authenticated_distinct_venue_triangles

class Tests(unittest.TestCase):
    def ready(self):
        pools={}
        for v,p,m in (("raydium_cpmm","one",["A","B"]),
                      ("orca","two",["B","C"]),
                      ("raydium_amm_v4","three",["C","A"])):
            pools[v]=[{"venue":v,"pool":p,"mints":m,"slot":17,"authenticated":True}]
        return {"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
                "authenticated_pools":pools}
    def test_three_source_pools_captured_without_signed_success_claim(self):
        r=self.ready()
        candidates=authenticated_distinct_venue_triangles(r["authenticated_pools"])
        chosen=next(i for i,x in enumerate(candidates) if x["route_venues"]==
                    ["raydium_cpmm","orca","raydium_amm_v4"])
        def snapshot(rpc,pool,venue):
            return next(x for x in r["authenticated_pools"][venue] if x["pool"]==pool)
        def extras(rpc,venue,pool,mints):
            return [pool,"shared"],{"source_proof":True}
        def rpc_call(rpc,method,args):
            self.assertEqual(method,"getMultipleAccounts")
            return {"context":{"slot":17},"value":[
                {"owner":"source","data":["AQ==","base64"],"lamports":1,"executable":False}
                for _ in args[0]]}
        with tempfile.TemporaryDirectory() as folder,patch(
             "arb.next_ten_pair_fixture_export.snapshot",side_effect=snapshot),patch(
             "arb.next_ten_pair_fixture_export.venue_accounts",side_effect=extras),patch(
             "arb.next_ten_pair_fixture_export.call",side_effect=rpc_call),patch(
             "arb.next_ten_pair_fixture_export.program_data_accounts",
             return_value={"executable":{"data":["AQ==","base64"]}}),patch(
             "arb.source_snapshot_manifest.verify",return_value=None):
            path=Path(folder)/"triangle.json"
            result=export_three_venue("http://127.0.0.1:8899",r,chosen,path)
            import json
            evidence=json.loads(path.read_text())
        self.assertEqual(result["status"],"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE")
        self.assertEqual(len(evidence["leg_evidence_by_index"]),3)
        self.assertEqual(evidence["state_account_count"],4)
        self.assertEqual(evidence["route_mints"],["A","B","C","A"])
        self.assertFalse(evidence["signed_atomic_simulation_verified"])
        self.assertFalse(evidence["broadcast"])
    def test_missing_candidate_rejected(self):
        with self.assertRaises(ValueError):
            export_three_venue("http://127.0.0.1:8899",self.ready(),100,"/tmp/unused")
    def test_unauthenticated_source_rejected(self):
        r=self.ready();r["source"]="unknown"
        with self.assertRaises(ValueError):
            export_three_venue("http://127.0.0.1:8899",r,0,"/tmp/unused")
if __name__=="__main__":unittest.main()
