import unittest
from arb.venue_watchlist import RECOGNIZED_UNSUPPORTED
from arb.onchain_pool_discovery import VENUES
class WatchlistTests(unittest.TestCase):
    def test_legacy_dex_programs_not_executable(self):
        self.assertIn("orca_token_swap_v1",RECOGNIZED_UNSUPPORTED.values())
        self.assertIn("raydium_amm_v4",RECOGNIZED_UNSUPPORTED.values())
        self.assertTrue(all(v not in VENUES for v in RECOGNIZED_UNSUPPORTED.values()))
