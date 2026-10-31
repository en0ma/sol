import unittest
from unittest.mock import patch
from arb.pool_registry_ingest import merge_identities,ingest
class IngestTests(unittest.TestCase):
    def test_duplicate_and_unknown_ignored(self):
        current=[{"venue":"orca","address":"1"*32}]
        discovery={"status":"PARTIAL","pools":[{"venue":"orca","address":"1"*32},
           {"venue":"meteora_dlmm","address":"2"*32},{"venue":"unknown","address":"3"*32}]}
        merged,new=merge_identities(current,discovery)
        self.assertEqual(new,1)
        self.assertEqual(len(merged),2)
    @patch("arb.pool_registry_ingest.refresh")
    def test_fresh_validation_required(self,refresh):
        refresh.return_value={"verified_pools":[],"rejected_count":1,"rejected":[{"reason":"missing"}]}
        result=ingest("rpc",[],{"pools":[{"venue":"orca","address":"1"*32}]})
        self.assertEqual(result["registry"]["pools"],[])
        self.assertEqual(result["rejected_count"],1)
        refresh.assert_called_once()
    def test_history_report_candidate_merge(self):
        merged,new=merge_identities([],{"pools":[
            {"venue":"raydium_cpmm","address":"5"*32,"verified":True,"slot":99}]})
        self.assertEqual(new,1)
        self.assertEqual(merged[0]["address"],"5"*32)
    def test_unbounded_rejected(self):
        with self.assertRaises(ValueError):merge_identities([],{"pools":[{}]*201})
