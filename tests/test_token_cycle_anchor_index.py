import json
import unittest
from unittest.mock import patch
from arb.token_cycle_graph import fetch_anchor_pool_hints, candidate_cycles, SOL, USDC

RAY="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"
A="7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm"
B="7JuwJuNU88gurFnyWeiyGKbFmExMWcmRZntn9imEzdny"
C="Czfq3xZZDmsdGdUyrNLtRhGc47cXcZtLG4crryfu44zE"

class Response:
    def __init__(self, pairs): self.data=json.dumps(pairs).encode()
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size): return self.data[:size]

def pair(address,dex,mint_a,mint_b):
    return {"chainId":"solana","pairAddress":address,"dexId":dex,
            "baseToken":{"address":mint_a},"quoteToken":{"address":mint_b}}

class AnchorIndexTests(unittest.TestCase):
    @patch("arb.token_cycle_graph.urlopen")
    def test_two_anchors_make_sol_ray_usdc_sol_triangle(self, fetch):
        fetch.side_effect=[
            Response([pair(A,"orca",SOL,RAY),pair(C,"orca",SOL,USDC),
                      pair(B,"raydium",RAY,USDC)]),
            Response([pair(B,"raydium",RAY,USDC),pair(C,"orca",SOL,USDC)])]
        edges, errors=fetch_anchor_pool_hints()
        self.assertFalse(errors)
        self.assertEqual(len(edges),3)
        graph=candidate_cycles(edges,starts=(SOL,))
        self.assertTrue(any(c["tokens"]==[SOL,RAY,USDC,SOL]
                            for c in graph["cycles"]))
        self.assertTrue(all(not c["actionable"] for c in graph["cycles"]))

    @patch("arb.token_cycle_graph.urlopen")
    def test_wrong_anchor_is_ignored(self, fetch):
        fetch.return_value=Response([pair(A,"orca",RAY,USDC)])
        hints, errors=fetch_anchor_pool_hints(anchors=(SOL,))
        self.assertEqual(hints, [])
        self.assertEqual(errors, [])
