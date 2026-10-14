import unittest
from arb.discover_raydium import discover, PROGRAMS, SOL, USDC

class DiscoveryTests(unittest.TestCase):
    def test_filters_untrusted_api_pool_owners_and_mints(self):
        good = {"id": "pool1", "programId": PROGRAMS["Raydium CLMM"],
                "mintA": {"address": SOL}, "mintB": {"address": USDC}, "tvl": 5000}
        spoofed = {**good, "id": "pool2", "programId": "other"}
        wrong_pair = {**good, "id": "pool3", "mintB": {"address": "notUSDC"}}
        self.assertEqual([p["address"] for p in discover(
            lambda _: {"success": True, "data": {"data": [good, spoofed, wrong_pair]}})], ["pool1"])

    def test_failed_api_rejected(self):
        with self.assertRaises(ValueError):
            discover(lambda _: {"success": False})
