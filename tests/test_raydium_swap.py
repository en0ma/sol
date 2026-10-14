import unittest
from arb.raydium_swap import encode,DISCRIMINATOR
class RaydiumSwapTests(unittest.TestCase):
    def test_encoding(self):
        d=encode(1000000,1)
        self.assertEqual(len(d),24)
        self.assertEqual(d[:8],DISCRIMINATOR)
        self.assertEqual(int.from_bytes(d[8:16],"little"),1000000)
    def test_invalid(self):
        for n in (0,-1,1<<64):
            with self.assertRaises(ValueError):encode(n,1)
