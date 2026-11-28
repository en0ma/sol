import json
import unittest
from unittest.mock import patch,MagicMock
from arb.orca_legacy_public_index import parse_candidates,discover,list_dexes

POOL="58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2"

def envelope(tvl="15000",address=POOL,next_link=None):
    return {"data":[{"id":"solana_"+address,
                     "attributes":{"address":address,"reserve_in_usd":tvl}}],
            "links":{"next":next_link}}

class OrcaLegacyIndexTests(unittest.TestCase):
    def test_liquidity_and_invalid_records(self):
        self.assertEqual(parse_candidates(envelope()),[POOL])
        self.assertEqual(parse_candidates(envelope(tvl="500")),[])
        self.assertEqual(parse_candidates(envelope(tvl="NaN")),[])
        self.assertEqual(parse_candidates(envelope(address="invalid")),[])

    def test_no_token_filter_in_paged_requests(self):
        with patch("arb.orca_legacy_public_index._get",
                   return_value=envelope()) as get:
            self.assertEqual(discover(dex_id="orca",max_pages=3),[POOL])
        url=get.call_args.args[0]
        self.assertIn("/networks/solana/dexes/orca/pools?",url)
        self.assertNotIn("token",url)
        self.assertNotIn("mint",url)

    def test_rejects_invalid_limits(self):
        with self.assertRaises(ValueError):
            discover(dex_id="orca",max_pages=0)
        with self.assertRaises(ValueError):
            parse_candidates(envelope(),min_liquidity_usd=-1)

    def test_catalog_returns_provenance_not_version_proof(self):
        with patch("arb.orca_legacy_public_index._get",
                   return_value={"data":[{"id":"orca_whirlpool",
                                           "attributes":{"name":"Orca Whirlpool"}}],
                                 "links":{"next":None}}):
            self.assertEqual(list_dexes(),{"orca_whirlpool":"Orca Whirlpool"})

if __name__=="__main__":
    unittest.main()
