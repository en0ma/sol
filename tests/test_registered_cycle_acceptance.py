import hashlib
import unittest
from arb.registered_cycle_acceptance import (
    verify_original_account_snapshot,screen_signed_cycle_net_acceptance)


def source():
    raw=b"actual-account-data"
    sha=hashlib.sha256(raw).hexdigest()
    row={"address":"poolA","owner":"programA","slot":22,
         "lamports":500,"executable":False}
    expected={"expected_owner":"programA","expected_address":"poolA",
              "expected_slot":22,"expected_sha256":sha}
    return row,raw,expected


class FinalGates(unittest.TestCase):
    def test_source_integrity_not_source_authenticity(self):
        row,raw,expected=source()
        out=verify_original_account_snapshot(row,raw,**expected)
        self.assertEqual(out["source_sha256"],expected["expected_sha256"])
        self.assertFalse(out["upstream_origin_independently_authenticated"])
        for altered,blob in (({**row,"slot":23},raw),
                             ({**row,"owner":"other"},raw),
                             ({**row,"lamports":True},raw),
                             (row,b"modified"),(row,b"")):
            with self.assertRaises(ValueError):
                verify_original_account_snapshot(altered,blob,**expected)

    def test_all_four_acceptance_gates_fail_closed(self):
        row,raw,expected=source()
        original=verify_original_account_snapshot(row,raw,**expected)
        second={**original,"account_address":"poolB"}
        fee={"status":"LOCAL_FEE_EVIDENCE_CORRELATED_NOT_AUTHENTICATED",
             "independent_fee_paid_verified":False,"fee_lamports":None,
             "actionable":False,"live_execution_approved":False,"broadcast":False}
        route={"legs":[{"pool":"poolA"},{"pool":"poolB"}]}
        signed={"status":"unsigned"}
        costs={"network_fee":0,"priority_fee":0,"tip":0,
               "flash_loan_fee":0,"setup_rent_net":0,"other":0}
        result=screen_signed_cycle_net_acceptance(route,signed,fee,
            source_accounts=[original,second],fee_components=costs)
        self.assertIsNone(result["accepted_net_profit_base_units"])
        self.assertFalse(result["net_profitability_verified"])
        self.assertFalse(result["actionable"])
        self.assertEqual(result["source_account_count"],2)
        self.assertTrue(all(value is False for value in result["gates"].values()))
        with self.assertRaises(ValueError):
            screen_signed_cycle_net_acceptance(route,signed,{**fee,"fee_lamports":500},
                source_accounts=[original,second])
        with self.assertRaises(ValueError):
            screen_signed_cycle_net_acceptance(route,signed,fee,
                source_accounts=[original,{**second,"source_slot":23}])
        with self.assertRaises(ValueError):
            screen_signed_cycle_net_acceptance(route,signed,fee,
                source_accounts=[original,second],
                fee_components={**costs,"tip":True})
        with self.assertRaises(ValueError):
            screen_signed_cycle_net_acceptance(route,signed,fee,
                source_accounts=[original,second],
                fee_components={"network_fee":0})


if __name__=="__main__":
    unittest.main()
