import unittest
from arb.next_ten_atomic_routes import ALL_42,REMAINING_42,route_batch
from arb.forty_two_atomic_evidence import reconcile_forty_two
from arb.live_pool_state_registry import PoolStateRegistry

def pool(venue,address,a,b,slot=100):
    return {"authenticated":True,"venue":venue,"pool":address,
            "mints":[a,b],"slot":slot,"active":True}

class FortyTwoAndLiveStateTests(unittest.TestCase):
    def test_inventory_complete_unique_and_shardable(self):
        self.assertEqual(len(ALL_42),42)
        self.assertEqual(len(REMAINING_42),24)
        self.assertEqual(len(route_batch("remaining")),24)
        self.assertEqual(set(ALL_42),set(route_batch("all")))
    def test_disjoint_remaining_pair_shards_cover_inventory(self):
        from arb.next_ten_atomic_routes import pair_shards
        shards=pair_shards(shards=4)
        self.assertEqual(len(shards),4)
        self.assertEqual(set(x for shard in shards for x in shard),set(REMAINING_42))
        self.assertEqual(sum(len(shard) for shard in shards),24)
        self.assertTrue(all(len(shard)==6 for shard in shards))
        with self.assertRaises(ValueError):
            pair_shards(shards=0)
    def test_full_matrix_refuses_mock_or_missing_receipts(self):
        report=reconcile_forty_two({})
        self.assertEqual(report["ordered_pair_verified"],0)
        self.assertEqual(report["ordered_pair_missing_or_unverified"],42)
        with self.assertRaises(ValueError):
            reconcile_forty_two({("fake","venue"):{"status":"VERIFIED"}})
    def test_incremental_registry_discovers_and_invalidates_cycles(self):
        reg=PoolStateRegistry(max_slot_lag=5)
        reg.ingest(pool("orca","a","A","B"))
        self.assertEqual(reg.routes(start_mints=["A"])["candidate_count"],0)
        reg.ingest(pool("cpmm","b","A","B",101))
        self.assertEqual(reg.routes(start_mints=["A"])["candidate_count"],2)
        self.assertFalse(reg.routes(start_mints=["A"])["broadcast"])
        reg.invalidate("cpmm","b",102)
        self.assertEqual(reg.routes(start_mints=["A"])["candidate_count"],0)
    def test_stale_and_untrusted_updates_fail_closed(self):
        reg=PoolStateRegistry(max_slot_lag=3)
        reg.ingest(pool("orca","a","A","B",20))
        with self.assertRaises(ValueError):reg.ingest(pool("orca","a","A","B",20))
        with self.assertRaises(ValueError):reg.ingest(pool("cpmm","b","A","B",10))
        bad=pool("cpmm","c","A","B",21)
        bad["authenticated"]=False
        with self.assertRaises(ValueError):reg.ingest(bad)
    def test_large_advance_invalidates_stale_cycle(self):
        reg=PoolStateRegistry(max_slot_lag=2)
        reg.ingest(pool("orca","a","A","B",10))
        reg.ingest(pool("cpmm","b","A","B",11))
        reg.ingest(pool("dlmm","c","C","D",20))
        self.assertEqual(reg.routes(start_mints=["A"])["candidate_count"],0)
if __name__=="__main__":unittest.main()
