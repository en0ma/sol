import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from arb.m5_existing_source_research import evaluate
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

class ExistingSourceResearchTests(unittest.TestCase):
    def test_authentic_indices_join_signed_results_without_inventing_profit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/"source";signed=root/"signed"
            source.mkdir();signed.mkdir()
            (source/"summary.json").write_text(json.dumps({"routes":[
                {"index":4,"status":"SOURCE_FIXTURE_BLOCKED"},
                {"index":7,"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE",
                 "fixture":"triangle-07.json"}],**SAFE}))
            (source/"triangle-07.json").write_text(json.dumps({"route_mints":["A","B","C","A"]}))
            (signed/"summary.json").write_text(json.dumps({"routes":[{
                "index":7,"status":"SIGNED_TRIANGLE_OBSERVED",
                "independent_signed_accepted":True,"gross_start_mint_delta":6,
                "economics_status":"COST_EVIDENCE_BLOCKED"}],**SAFE}))
            quote={"fully_quoted":1,"blocked":0,"positive_gross":1,
                "ranked":[{"index":0,"status":"GROSS_INDICATIVE_ONLY",
                           "gross_delta_start_mint_base_units":10}],
                "all_results":[{"index":0,"status":"GROSS_INDICATIVE_ONLY"}]}
            with patch("arb.m5_existing_source_research.rank",return_value=quote) as ranker:
                result=evaluate(source,amount_in=100,observed_unix=123,signed_dir=signed)
            ranker.assert_called_once()
            self.assertEqual(result["ranked_routes"][0]["source_batch_route_index"],7)
            self.assertTrue(result["ranked_routes"][0]["signed_observation"]["independent_signed_accepted"])
            self.assertEqual(result["ranked_routes"][0]["signed_observation"]["gross_start_mint_delta"],6)
            self.assertFalse(result["net_profit_verified"])
            self.assertFalse(result["broadcast"])

    def test_empty_source_manifest_is_truthful(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/"summary.json").write_text(json.dumps({"routes":[],**SAFE}))
            result=evaluate(d,amount_in=100,observed_unix=123)
            self.assertEqual(result["source_exported"],0)
            self.assertEqual(result["positive_gross_indicative"],0)
            self.assertEqual(result["signed_receipts_available"],0)

    def test_source_path_and_unsafe_signed_summary_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/"source";signed=root/"signed"
            source.mkdir();signed.mkdir()
            (source/"summary.json").write_text(json.dumps({"routes":[{
                "index":0,"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE",
                "fixture":"../../escape.json"}],**SAFE}))
            with self.assertRaises(ValueError):
                evaluate(source,amount_in=100,observed_unix=123)
            (source/"summary.json").write_text(json.dumps({"routes":[],**SAFE}))
            (signed/"summary.json").write_text(json.dumps({"routes":[],"broadcast":True,
                "actionable":False,"live_execution_approved":False}))
            with self.assertRaises(ValueError):
                evaluate(source,amount_in=100,observed_unix=123,signed_dir=signed)

if __name__=="__main__":
    unittest.main()
