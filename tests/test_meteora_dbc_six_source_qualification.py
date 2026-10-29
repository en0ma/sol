"""Six DBC original-source gate: unique independent evidence, not signed status."""
import unittest
from unittest.mock import patch
from arb.meteora_dbc_six_source_qualification import qualify


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


if __name__=="__main__":unittest.main()
