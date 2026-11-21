import unittest
from arb.next_ten_fork_pool_probe import select_distinct_triangle_coverage as select
class Tests(unittest.TestCase):
    def test_prefers_new_venue_triples_over_duplicate_orientations(self):
        c=[{"route_venues":["orca","raydium_cpmm","raydium_amm_v4"]},
           {"route_venues":["raydium_cpmm","raydium_amm_v4","orca"]},
           {"route_venues":["orca","meteora_dlmm","raydium_clmm"]}]
        self.assertEqual(select(c,maximum=2),[c[0],c[2]])
    def test_untrusted_candidate_rejected(self):
        with self.assertRaises(ValueError):
            select([{"route_venues":["orca","orca","raydium_clmm"]}])
if __name__=="__main__":unittest.main()
