import unittest
from arb.clmm_local_alt import require_local
class GuardTests(unittest.TestCase):
    def test_only_local(self):
        for url in ("https://api.mainnet-beta.solana.com","https://localhost:8899","http://evil.example:8899"):
            with self.assertRaises(ValueError):require_local(url)
        require_local("http://127.0.0.1:8899")
