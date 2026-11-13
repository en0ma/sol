import unittest
from arb.ci_job_runtime_audit import audit,seconds
class RuntimeAudits(unittest.TestCase):
    def test_reports_slow_job_and_step_without_disabling_critical_job(self):
        jobs=[{"name":"authenticated-source-fork","conclusion":"success",
               "started_at":"2026-10-24T12:00:00Z","completed_at":"2026-10-24T12:12:00Z",
               "steps":[{"name":"Export","started_at":"2026-10-24T12:01:00Z",
                         "completed_at":"2026-10-24T12:05:00Z"}]}]
        result=audit(jobs)
        self.assertTrue(any(r["reason"]=="LONG_RUNTIME" for r in result["recommendations"]))
        self.assertTrue(result["no_automatic_job_disabling"])
        self.assertEqual(result["upstream_rpc_calls"],0)
        self.assertEqual(result["jobs"][0]["slow_steps"][0]["duration_seconds"],240)
    def test_missing_required_jobs_are_not_treated_as_passed(self):
        result=audit([])
        self.assertTrue(any(r["reason"]=="REQUIRED_JOB_NOT_IN_RUN" for r in result["recommendations"]))
    def test_invalid_job_timestamps_remain_unknown(self):
        self.assertIsNone(seconds("bad","bad"))
if __name__=="__main__":unittest.main()
