import json
import unittest
from unittest.mock import patch
from arb.cross_venue_discovery import indexed_candidates
from arb.orca_whirlpool import SOL, USDC

ORCA = "7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm"
RAY = "7JuwJuNU88gurFnyWeiyGKbFmExMWcmRZntn9imEzdny"

class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, count): return self.payload[:count]

class PublicPoolIndexTests(unittest.TestCase):
    @patch("arb.cross_venue_discovery.urlopen")
    def test_only_exact_sol_usdc_addresses_survive(self, urlopen):
        def pair(dex, address, base=SOL, quote=USDC, chain="solana"):
            return {"chainId":chain,"dexId":dex,"pairAddress":address,
                    "baseToken":{"address":base},"quoteToken":{"address":quote}}
        urlopen.return_value = FakeResponse([
            pair("orca", ORCA), pair("orca", ORCA),
            pair("raydium", RAY, USDC, SOL),
            pair("raydium", ORCA, base="WrongMint"),
            pair("orca", RAY, chain="ethereum"),
            pair("unknown", ORCA),
            pair("orca", "not-a-valid-pubkey")])
        result = indexed_candidates()
        self.assertEqual(result, {"orca":[ORCA], "raydium_cpmm":[RAY]})

    @patch("arb.cross_venue_discovery.urlopen")
    def test_unexpected_response_fails_closed(self, urlopen):
        urlopen.return_value = FakeResponse({"error": "rate limit"})
        with self.assertRaises(ValueError):
            indexed_candidates()
