import unittest
from arb.m5_seven_venue_public_hints import merge,choose_connectivity_leads
from arb.next_ten_fork_pool_probe import PROGRAMS
BASE={"pools":[{"venue":"orca","address":"1"*32,"mints":["A","B"]}]}
class BroadenedHintsTests(unittest.TestCase):
    def test_all_venue_feeds_keep_pinned_priority_and_untrusted_flags(self):
        feeds={v:[] for v in PROGRAMS}
        feeds["orca"]=["1"*32,"2"*32]
        feeds["raydium_amm_v4"]=["3"*32]
        feeds["meteora_dlmm"]=[{"address":"4"*32}]
        r=merge(BASE,feeds,limit_per_venue=2)
        self.assertEqual(r["pools"][0]["address"],"1"*32)
        self.assertEqual(r["discovery"]["coverage"]["orca"]["appended"],1)
        self.assertEqual(r["discovery"]["coverage"]["raydium_amm_v4"]["appended"],1)
        self.assertFalse(r["pools"][1]["onchain_authenticated"])
        self.assertFalse(r["discovery"]["broadcast"])
        self.assertEqual(set(r["discovery"]["coverage"]),set(PROGRAMS))
    def test_limits_and_duplicate_scope(self):
        feeds={v:[] for v in PROGRAMS}
        feeds["orca"]=["2"*32,"3"*32,"2"*32]
        feeds["meteora_dlmm"]=["1"*32]
        r=merge(BASE,feeds,limit_per_venue=2)
        self.assertEqual(r["discovery"]["coverage"]["orca"]["total_candidates"],2)
        self.assertEqual(r["discovery"]["coverage"]["meteora_dlmm"]["total_candidates"],1)
    def test_greedy_mint_connectivity_prefers_bridge_over_hub_leaf(self):
        registry={"pools":[
            {"venue":"orca","address":"1"*32,"mints":["A","B"]},
            {"venue":"orca","address":"2"*32,"mints":["B","C"]}]}
        leads=[{"address":"3"*32,"mints":["A","D"]},
               {"address":"4"*32,"mints":["A","C"]},
               {"address":"5"*32,"mints":["A","E"]}]
        chosen=choose_connectivity_leads(leads,registry,limit=2)
        self.assertEqual(chosen[0],"4"*32)
        self.assertEqual(len(chosen),2)
        with self.assertRaises(ValueError):
            choose_connectivity_leads(leads,registry,limit=0)

    def test_invalid_pool_address_fails_closed(self):
        feeds={v:[] for v in PROGRAMS}
        with self.assertRaises(ValueError):
            merge({"pools":[{"venue":"orca","address":"not-address"}]},feeds)
        with self.assertRaises(ValueError):
            merge(BASE,{"orca":[]})
        with self.assertRaises(ValueError):
            merge(BASE,feeds,limit_per_venue=0)
if __name__=="__main__":unittest.main()
