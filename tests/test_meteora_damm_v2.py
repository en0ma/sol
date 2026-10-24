import unittest
from unittest.mock import patch
from arb.meteora_damm_v2 import decode,SIZE,DISC
from arb.onchain_pool_discovery import search_pair,MINTS
class MeteoraDammV2Tests(unittest.TestCase):
    def fixture(self):
        raw=bytearray(SIZE);raw[:8]=DISC
        for i,offset in enumerate((168,200,232,264),1):
            raw[offset:offset+32]=bytes([i])*32
        raw[360:376]=(1<<64).to_bytes(16,"little")
        raw[456:472]=(1<<64).to_bytes(16,"little")
        return raw
    def test_official_layout(self):
        state=decode(bytes(self.fixture()))
        self.assertEqual(state["sqrt_price"],1<<64)
        self.assertEqual(state["liquidity"],1<<64)
    def test_bad_discriminator(self):
        with self.assertRaises(ValueError):decode(bytes(SIZE))
    @patch("arb.onchain_pool_discovery.call",return_value=[])
    def test_mint_filters(self,call):
        search_pair("rpc","meteora_damm_v2",MINTS["WSOL"],MINTS["USDC"])
        f=call.call_args_list[0].args[2][1]["filters"]
        self.assertEqual([x["memcmp"]["offset"] for x in f[1:]],[168,200])
