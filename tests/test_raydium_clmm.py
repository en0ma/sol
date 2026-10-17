import unittest
from arb.raydium_clmm import SIZE,DISC,decode
class RaydiumClmmTests(unittest.TestCase):
    def fixture(self):
        b=bytearray(SIZE);b[:8]=DISC
        for i,offset in enumerate((9,41,73,105,137,169,201),1):
            b[offset:offset+32]=bytes([i])*32
        b[235:237]=(16).to_bytes(2,"little")
        b[237:253]=(1000000).to_bytes(16,"little")
        b[253:269]=(1<<64).to_bytes(16,"little")
        return b
    def test_layout_and_offsets(self):
        s=decode(bytes(self.fixture()))
        self.assertEqual(s["tick_spacing"],16)
        self.assertEqual(s["liquidity"],1000000)
        self.assertEqual(s["sqrt_price_x64"],1<<64)
    def test_rejects_bad_layout(self):
        with self.assertRaises(ValueError):decode(bytes(SIZE))
    def test_rejects_invalid_price(self):
        b=self.fixture();b[253:269]=bytes(16)
        with self.assertRaises(ValueError):decode(bytes(b))
