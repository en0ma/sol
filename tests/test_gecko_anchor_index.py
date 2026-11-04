import json
import unittest
from unittest.mock import patch
from arb.gecko_anchor_index import fetch_gecko_anchor_hints
from arb.orca_whirlpool import SOL, USDC

POOL="7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm"

class Response:
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,size): return self.data[:size]
    def __init__(self,obj): self.data=json.dumps(obj).encode()

def document(liquidity="125000", other=USDC):
    return {"data":[{"attributes":{"address":POOL,"reserve_in_usd":liquidity},
            "relationships":{"base_token":{"data":{"id":"solana_"+SOL}},
                             "quote_token":{"data":{"id":"solana_"+other}},
                             "dex":{"data":{"id":"orca"}}}}],
            "included":[{"id":"solana_"+SOL,"attributes":{"address":SOL}},
                        {"id":"solana_"+other,"attributes":{"address":other}}]}

class GeckoSourceTests(unittest.TestCase):
    @patch("arb.gecko_anchor_index.urlopen")
    def test_liquid_anchor_pool_is_deduplicated_across_pages(self, urlopen):
        urlopen.return_value=Response(document())
        result, errors=fetch_gecko_anchor_hints(anchors=(SOL,))
        self.assertFalse(errors)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["mints"],[SOL,USDC])
        self.assertEqual(result[0]["index_liquidity_usd"],125000)
        self.assertEqual(result[0]["candidate_source"],"UNTRUSTED_GECKOTERMINAL")

    @patch("arb.gecko_anchor_index.urlopen")
    def test_insufficient_liquidity_is_excluded(self, urlopen):
        urlopen.return_value=Response(document(liquidity="500"))
        result, errors=fetch_gecko_anchor_hints(anchors=(SOL,))
        self.assertEqual(result,[])
        self.assertFalse(errors)

    @patch("arb.gecko_anchor_index.urlopen")
    def test_malformed_api_does_not_invent_candidates(self, urlopen):
        urlopen.return_value=Response({"errors":["rate limited"]})
        result, errors=fetch_gecko_anchor_hints(anchors=(SOL,))
        self.assertEqual(result,[])
        self.assertTrue(errors)
