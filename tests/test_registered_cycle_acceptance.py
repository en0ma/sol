import hashlib
import unittest
import base64
from unittest.mock import patch
from arb.registered_cycle_acceptance import (
    verify_original_account_snapshot,screen_signed_cycle_net_acceptance,
    inspect_upstream_original_account)


def source():
    raw=b"actual-account-data"
    sha=hashlib.sha256(raw).hexdigest()
    row={"address":"poolA","owner":"programA","slot":22,
         "lamports":500,"executable":False}
    expected={"expected_owner":"programA","expected_address":"poolA",
              "expected_slot":22,"expected_sha256":sha}
    return row,raw,expected


class FinalGates(unittest.TestCase):
    @patch("arb.rpc.call")
    def test_original_upstream_rpc_observation_not_independent_authentication(self, call):
        blob=b"real-original-pool-account"
        call.return_value={"context":{"slot":99},"value":{
            "owner":"expectedProgram","lamports":4500,"executable":False,
            "data":[base64.b64encode(blob).decode(),"base64"]}}
        result=inspect_upstream_original_account(
            "https://rpc.example.org",address="pool",
            expected_owner="expectedProgram",min_context_slot=98)
        self.assertEqual(result["source_sha256"],hashlib.sha256(blob).hexdigest())
        self.assertFalse(result["upstream_origin_independently_authenticated"])
        self.assertFalse(result["broadcast"])
        self.assertEqual(call.call_args.args[1],"getAccountInfo")
        self.assertEqual(call.call_args.args[2][1]["minContextSlot"],98)
        for bad in ("http://rpc.example.org","http://127.0.0.1:8899",
                    "https://localhost:8899","https://user:secret@rpc.example.org"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    inspect_upstream_original_account(
                        bad,address="pool",expected_owner="expectedProgram")
        for altered in (
            {"context":{"slot":97},"value":call.return_value["value"]},
            {"context":{"slot":99},"value":{**call.return_value["value"],"owner":"wrong"}},
            {"context":{"slot":99},"value":{**call.return_value["value"],"lamports":True}},
            {"context":{"slot":99},"value":{**call.return_value["value"],"data":["bad!","base64"]}},
            {"context":{"slot":99},"value":{**call.return_value["value"],"data":["","base64"]}},
        ):
            with self.subTest(altered=altered):
                call.return_value=altered
                with self.assertRaises(ValueError):
                    inspect_upstream_original_account(
                        "https://rpc.example.org",address="pool",
                        expected_owner="expectedProgram",min_context_slot=98)

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
