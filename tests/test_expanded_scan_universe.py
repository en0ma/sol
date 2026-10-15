import unittest
from arb.onchain_pool_discovery import MINTS,VENUES
from arb.opportunity_graph import cycles
class ExpandedUniverseTests(unittest.TestCase):
    def test_ray_in_scan_universe(self):
        self.assertEqual(MINTS["RAY"],"4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R")
    def test_five_decoder_venues(self):
        self.assertGreaterEqual(len(VENUES),5)
    def test_unverified_pool_not_a_route(self):
        x=[{"venue":"meteora_dlmm","address":"fake","verified":False,"mints":["a","b"]}]
        self.assertEqual(cycles(x,anchors=["a"]),[])
