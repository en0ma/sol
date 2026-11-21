"""Mint diagnostics must never upgrade failed routes to signed coverage."""
import unittest

from arb.m5_three_hop_mint_diagnostics import build_report


def shards():
    rows=[]
    for i in range(10):
        attempted=[f"route-{i}-{j}" for j in range(14)]
        verified=attempted[:-1]
        failed={
            "id":attempted[-1],
            "start_mint":"MINT_MISSING",
            "venue":"orca",
            "pool":"POOL",
            "error_code":6036,
            "attempted_exact_input_base_units":[100000,1000000],
        }
        rows.append({
            "shard":i,
            "route_ids":attempted,
            "verified_route_ids":verified,
            "selected_start_mints":["MINT_MISSING",f"MINT_VERIFIED_{i}"],
            "verified_start_mints":[f"MINT_VERIFIED_{i}"],
            "failures":[failed],
        })
    return rows


class MintGapReportTests(unittest.TestCase):
    def test_unverified_mint_is_not_counted_as_signed(self):
        report=build_report(shards())
        self.assertEqual(report["attempted_routes"],140)
        self.assertEqual(report["verified_routes"],130)
        self.assertEqual(report["signed_verified_start_mints"],10)
        self.assertEqual(report["source_captured_but_not_signed_verified_start_mints"],1)
        gap=report["unverified_start_mints"][0]
        self.assertEqual(gap["start_mint"],"MINT_MISSING")
        self.assertEqual(gap["failure_reason_counts"],{"orca:6036":10})
        self.assertEqual(gap["failed_routes"][0]
                         ["attempted_exact_input_base_units"],[100000,1000000])
        self.assertIs(gap["signed_and_rollback_verified"],False)
        self.assertFalse(report["actionable"])
        self.assertFalse(report["broadcast"])

    def test_wrong_mint_binding_rejected(self):
        reports=shards()
        reports[0]["failures"][0]["start_mint"]="NOT_IN_SELECTED"
        with self.assertRaisesRegex(ValueError,"start mint"):
            build_report(reports)

    def test_duplicate_route_identity_rejected(self):
        reports=shards()
        reports[1]["route_ids"][0]=reports[0]["route_ids"][0]
        reports[1]["verified_route_ids"][0]=reports[0]["verified_route_ids"][0]
        with self.assertRaisesRegex(ValueError,"duplicate"):
            build_report(reports)

    def test_missing_shard_rejected(self):
        with self.assertRaisesRegex(ValueError,"ten"):
            build_report(shards()[:-1])

    def test_missing_failure_does_not_create_false_coverage(self):
        reports=shards()
        reports[0]["failures"]=[]
        with self.assertRaisesRegex(ValueError,"count mismatches"):
            build_report(reports)

    def test_no_gaps_after_genuine_verified_mint(self):
        reports=shards()
        reports[0]["verified_start_mints"].append("MINT_MISSING")
        report=build_report(reports)
        self.assertEqual(report["source_captured_but_not_signed_verified_start_mints"],0)
        self.assertEqual(report["unverified_start_mints"],[])


if __name__=="__main__":
    unittest.main()
