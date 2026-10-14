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

class ExactOutputTests(unittest.TestCase):
    def test_exact_output_encoding(self):
        from arb.raydium_swap import encode_exact_output,OUTPUT_DISCRIMINATOR
        data=encode_exact_output(1000000,10000)
        self.assertEqual(data[:8],OUTPUT_DISCRIMINATOR)
        self.assertEqual(int.from_bytes(data[8:16],"little"),1000000)
        self.assertEqual(int.from_bytes(data[16:24],"little"),10000)
