import unittest
from unittest.mock import patch
from arb.onchain_pool_discovery import search_pair,MINTS
class RaydiumClmmFilterTests(unittest.TestCase):
    @patch("arb.onchain_pool_discovery.call",return_value=[])
    def test_mint_offsets(self,call):
        search_pair("rpc","raydium_clmm",MINTS["WSOL"],MINTS["USDT"])
        filters=call.call_args_list[0].args[2][1]["filters"]
        self.assertEqual([f["memcmp"]["offset"] for f in filters[1:]],[73,105])
