"""Six DBC original-source gate: unique independent evidence, not signed status."""
import unittest
from unittest.mock import patch
from arb.meteora_dbc_six_source_qualification import qualify, validate_official_sdk_candidate


class SixDbcSources(unittest.TestCase):
    def test_reject_fewer_than_six(self):
        with self.assertRaisesRegex(ValueError,"six distinct"):
            qualify("https://readonly.invalid",count=5)

    def test_six_unique_and_independently_audited(self):
        pools=[{"pool":"source-pool-"+str(n)} for n in range(6)]
        source={"source_pools":pools}
        with patch("arb.meteora_dbc_six_source_qualification.run",return_value=source) as run, patch(
                "arb.meteora_dbc_six_source_qualification.independently_audit",
                return_value={"authenticated_source_pools":6}) as audit:
            result=qualify("https://readonly.invalid")
        self.assertEqual(run.call_args.kwargs["count"],6)
        self.assertEqual(audit.call_count,1)
        self.assertEqual(result["authenticated_source_pools"],6)
        self.assertEqual(result["signed_swaps_verified"],0)
        self.assertFalse(result["registry_admission_approved"])

    def test_duplicate_pool_rejected_before_audit(self):
        source={"source_pools":[{"pool":"repeated"} for _ in range(6)]}
        with patch("arb.meteora_dbc_six_source_qualification.run",return_value=source), patch(
                "arb.meteora_dbc_six_source_qualification.independently_audit") as audit:
            with self.assertRaisesRegex(ValueError,"unique"):
                qualify("https://readonly.invalid")
            audit.assert_not_called()

    def test_independent_source_audit_count_must_match(self):
        source={"source_pools":[{"pool":str(i)} for i in range(6)]}
        with patch("arb.meteora_dbc_six_source_qualification.run",return_value=source), patch(
            "arb.meteora_dbc_six_source_qualification.independently_audit",
            return_value={"authenticated_source_pools":5}
        ):
            with self.assertRaisesRegex(ValueError,"independent"):
                qualify("https://readonly.invalid")

    def test_unquotable_pool_is_rejected_before_six_source_admission(self):
        from unittest.mock import Mock
        from arb.meteora_dbc_seventh_candidate_capture import run
        hints={"hints":[{"address":"bad"},{"address":"good"}],
               "program_transactions_checked":2}
        def identity(_rpc,*,count,pool_addresses):
            return {"authenticated":1,"source_pools":[{"address":pool_addresses[0]}]}
        def state(_rpc,source):
            return {"pool":source["address"]}
        def sdk_screen(row):
            if row["pool"]=="bad":
                raise ValueError("DBC official SDK bidirectional quote screening failed")
        with patch("arb.meteora_dbc_seventh_candidate_capture.onchain_discover",return_value=hints), \\
             patch("arb.meteora_dbc_seventh_candidate_capture.capture",side_effect=identity), \\
             patch("arb.meteora_dbc_seventh_candidate_capture.capture_pool",side_effect=state):
            result=run("https://readonly.invalid",count=1,
                       candidate_validator=sdk_screen)
        self.assertEqual([p["pool"] for p in result["source_pools"]],["good"])
        self.assertEqual(result["rejected_candidate_count"],1)


if __name__=="__main__":unittest.main()
