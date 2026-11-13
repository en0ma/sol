"""DBC index discovery is only untrusted address selection."""
import unittest
from solders.pubkey import Pubkey
from arb.meteora_dbc_seventh_discovery import discover


def address(n):
    return str(Pubkey.from_bytes(bytes([n])*32))


class DbcDiscoveryTests(unittest.TestCase):
    def test_bounded_deduplicated_untrusted_hints(self):
        def fetch(url):
            self.assertIn("dex_name=meteora_dbc", url)
            return {"results":[{"address":address(1)},{"address":address(1)},
                               {"address":"not-a-pubkey"},{"address":address(2)}]}
        proof=discover(count=2,fetch=fetch)
        self.assertEqual(len(proof["hints"]),2)
        self.assertEqual(proof["authenticated_pools"],0)
        self.assertEqual(proof["signed_verified_pools"],0)
        self.assertFalse(proof["actionable"])

    def test_bad_index_schema_rejected(self):
        with self.assertRaisesRegex(ValueError,"response"):
            discover(count=1,fetch=lambda _: {"results":None})

    def test_invalid_count_rejected(self):
        with self.assertRaisesRegex(ValueError,"1-6"):
            discover(count=7,fetch=lambda _: None)


if __name__=="__main__":
    unittest.main()
