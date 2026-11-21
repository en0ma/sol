import unittest
from arb.next_ten_atomic_routes import route_batch

class OfflineAtomicShardingTests(unittest.TestCase):
    def test_all_remaining_routes_partitioned_without_duplication(self):
        routes=route_batch("remaining")
        pieces=[[r for i,r in enumerate(routes) if i%4==j] for j in range(4)]
        self.assertEqual([len(x) for x in pieces],[6]*4)
        self.assertEqual(set(sum(pieces,[])),set(routes))
        self.assertEqual(sum(map(len,pieces)),len(routes))
    def test_ten_route_shards_unchanged(self):
        self.assertEqual(len(route_batch("first")),10)
        self.assertEqual(len(route_batch("next")),10)

if __name__=="__main__":unittest.main()
