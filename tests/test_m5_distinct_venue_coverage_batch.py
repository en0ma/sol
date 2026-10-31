import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from arb.m5_distinct_venue_coverage_batch import source_batch,offline_batch
class Tests(unittest.TestCase):
    def pools(self):
        triples=(("orca","oa",["A","B"]),("raydium_cpmm","cp",["B","C"]),("raydium_amm_v4","v4",["C","A"]))
        return {v:[{"venue":v,"pool":p,"mints":m,"slot":8,"authenticated":True}] for v,p,m in triples}
    def test_multiple_read_only_exports_retained(self):
        with tempfile.TemporaryDirectory() as directory,patch("arb.m5_distinct_venue_coverage_batch.export_three_venue") as export:
            def produce(rpc,ready,index,path):
                Path(path).write_text(json.dumps({"index":index}))
                return {"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE"}
            export.side_effect=produce
            report=source_batch("http://127.0.0.1:8899",
                {"authenticated_pools":self.pools()},directory,maximum=3)
            self.assertEqual(report["attempted"],3)
            self.assertEqual(report["exported"],3)
            self.assertEqual(export.call_count,3)
            self.assertFalse(report["broadcast"])
    def test_source_auxiliary_account_evidence_exported_without_fee_invention(self):
        with tempfile.TemporaryDirectory() as directory,patch(
            "arb.m5_distinct_venue_coverage_batch.export_three_venue") as export,patch(
            "arb.m5_distinct_venue_coverage_batch.inspect_native_aux") as decode:
            def produce(rpc,ready,index,path):
                Path(path).write_text(json.dumps({"fixture":"captured"}))
                return {"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE"}
            export.side_effect=produce
            decode.return_value={"source_slot":123,"venues":[{"venue":"meteora_dlmm",
                "missing":["decoded_dynamic_fee_parameters"],"fully_priced":False}],
                "full_native_fee_pricing_verified":False}
            report=source_batch("http://127.0.0.1:8899",
                {"authenticated_pools":self.pools()},directory,maximum=1)
            self.assertEqual(report["native_auxiliary_diagnostics_captured"],1)
            evidence=json.loads((Path(directory)/"source-native-aux-00.json").read_text())
            self.assertFalse(evidence["full_native_fee_pricing_verified"])
            self.assertIn("decoded_dynamic_fee_parameters",report["routes"][0]["native_auxiliary_missing"])
            self.assertFalse(report["broadcast"])

    def test_signed_gate_controls_success_count(self):
        with tempfile.TemporaryDirectory() as source,tempfile.TemporaryDirectory() as output:
            root=Path(source)
            (root/"summary.json").write_text(json.dumps({"routes":[
                {"index":0,"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE","fixture":"triangle-00.json"},
                {"index":1,"status":"AUTHENTICATED_THREE_VENUE_SOURCE_FIXTURE","fixture":"triangle-01.json"}]}))
            for i in range(2):
                (root/("triangle-%02d.json"%i)).write_text(json.dumps({"route_venues":["orca","raydium_cpmm","raydium_amm_v4"],"route_pool_addresses":["p","q","r"],"route_mints":["A","B","C","A"]}))
            with patch("arb.m5_distinct_venue_coverage_batch.run_three_venue",
                       return_value={"status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED"}),patch(
                 "arb.m5_distinct_venue_coverage_batch.accept",side_effect=[{},ValueError("rollback missing")]),patch(
                 "arb.m5_distinct_venue_coverage_batch.compare",
                 return_value={"signed_execution_accepted":True,"independently_validated_quote_samples":0,"leg_comparisons":[]}):
                report=offline_batch("http://127.0.0.1:8899",source,output,observed_unix=100)
            self.assertEqual(report["independent_signed_accepted"],1)
            self.assertEqual(report["routes"][0]["price_measurement_status"],"PRICE_MEASUREMENT_BLOCKED")
            self.assertTrue((Path(output)/"native-aux-00.json").exists())
            self.assertTrue((Path(output)/"signed-price-experiment-00.json").exists())
            pricing=json.loads((Path(output)/"signed-price-experiment-00.json").read_text())
            self.assertEqual(pricing["observed_compared_samples"],0)
            self.assertFalse(pricing["broadcast"])
            self.assertEqual(report["independently_validated_quote_samples"],0)
            self.assertEqual(len(report["routes"]),2)
if __name__=="__main__":unittest.main()
