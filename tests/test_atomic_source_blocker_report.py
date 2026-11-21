import unittest
from arb.atomic_source_blocker_report import diagnose
from arb.next_ten_atomic_routes import route_batch

class SourceBlockerTests(unittest.TestCase):
    def test_diagnostic_separates_no_pool_no_overlap_and_export_failure(self):
        probes=[];summaries=[]
        for batch in ("first","next","remaining"):
            routes=route_batch(batch)
            rows=[]
            reports=[]
            for i,(a,b) in enumerate(routes):
                pool_count=1
                rows.append({"first_venue":a,"second_venue":b,
                             "candidate_count":1 if i==2 else 0})
                reports.append({"first_venue":a,"second_venue":b,
                                "status":"SOURCE_FIXTURE_BLOCKED",
                                "reason":"account unavailable"})
            probes.append({"authenticated_pools":{
                v:[{"pool":"p"}] for route in routes for v in route},
                "route_candidates":rows,"failed_pool_checks":[]})
            summaries.append({"routes":reports})
        report=diagnose(probes,summaries)
        self.assertEqual(report["counts_by_stage"]["ACCOUNT_OR_PROGRAM_EXPORT_FAILED"],3)
        self.assertEqual(report["counts_by_stage"]["NO_SHARED_AUTHENTICATED_MINT_PAIR"],41)
        self.assertEqual(report["rpc_calls_performed"],0)
        self.assertFalse(report["signed_atomic_execution_verified"])

if __name__=="__main__":unittest.main()
