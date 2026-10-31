import unittest
from unittest.mock import patch
from arb.meteora_dlmm import decode,SIZE,DISC
from arb.onchain_pool_discovery import search_pair,MINTS
class MeteoraDlmmTests(unittest.TestCase):
    def fixture(self):
        data=bytearray(SIZE);data[:8]=DISC
        for i,offset in enumerate((88,120,152,184),1):
            data[offset:offset+32]=bytes([i])*32
        data[80:82]=(25).to_bytes(2,"little")
        return data
    def test_pool_identity(self):
        state=decode(bytes(self.fixture()))
        self.assertEqual(state["bin_step"],25)
        self.assertEqual(state["status"],0)
    def test_bad_discriminator(self):
        with self.assertRaises(ValueError):decode(bytes(SIZE))
    @patch("arb.onchain_pool_discovery.call",return_value=[])
    def test_filtered_mint_offsets(self,call):
        search_pair("rpc","meteora_dlmm",MINTS["WSOL"],MINTS["USDT"])
        filters=call.call_args_list[0].args[2][1]["filters"]
        self.assertEqual([x["memcmp"]["offset"] for x in filters[1:]],[88,120])
