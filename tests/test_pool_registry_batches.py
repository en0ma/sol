import unittest
from unittest.mock import patch

from arb.pool_registry_batches import refresh_batched

def entry(i, venue="orca"):
    return {"venue":venue,"address":str(i).zfill(32)}

class BatchedRegistryTests(unittest.TestCase):
    @patch("arb.pool_registry_batches.refresh")
    def test_more_than_two_hundred_uses_strict_bounded_chunks(self, refresh):
        def check(rpc, entries):
            self.assertLessEqual(len(entries), 200)
            return {"verified_pools":[{"venue":e["venue"],"address":e["address"],
                                       "mints":["base","quote"],"slot":1} for e in entries],
                    "rejected":[]}
        refresh.side_effect=check
        report=refresh_batched("rpc",[entry(i) for i in range(401)],batch_size=200)
        self.assertEqual([len(call.args[1]) for call in refresh.call_args_list],[200,200,1])
        self.assertEqual(report["verified_count"],401)
        self.assertEqual(report["batch_count"],3)
        self.assertEqual(report["rejected_count"],0)
        self.assertFalse(report["broadcast"])

    @patch("arb.pool_registry_batches.refresh")
    def test_cross_batch_duplicate_never_validated_twice(self, refresh):
        refresh.side_effect=lambda rpc, entries: {
            "verified_pools":[{"venue":e["venue"],"address":e["address"],
                               "mints":["base","quote"],"slot":1} for e in entries],
            "rejected":[]}
        report=refresh_batched("rpc",[entry(1),entry(2),entry(1)],batch_size=1)
        self.assertEqual(report["verified_count"],2)
        self.assertEqual(report["rejected_count"],1)
        self.assertEqual(report["rejected"][0]["reason"],"DUPLICATE")
        self.assertEqual(report["status"],"PARTIAL")
        self.assertEqual(refresh.call_count,2)

    @patch("arb.pool_registry_batches.refresh")
    def test_rejections_remain_rejections(self, refresh):
        refresh.return_value={"verified_pools":[],"rejected":[
            {"venue":"orca","address":entry(1)["address"],"reason":"owner mismatch"}]}
        report=refresh_batched("rpc",[entry(1)])
        self.assertEqual(report["verified_count"],0)
        self.assertEqual(report["rejected_count"],1)
        self.assertEqual(report["status"],"PARTIAL")

    def test_invalid_budgets_fail_closed(self):
        for kwargs in ({"batch_size":201},{"batch_size":0},{"max_entries":2001}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                refresh_batched("rpc",[],**kwargs)
        with self.assertRaises(ValueError):
            refresh_batched("rpc",[entry(i) for i in range(2001)])
