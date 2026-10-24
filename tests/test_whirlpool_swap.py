import unittest
from arb.whirlpool_swap import encode_swap, DISC, MIN_SQRT, MAX_SQRT

class WhirlpoolSwapEncodingTests(unittest.TestCase):
    def test_anchor_payload(self):
        data=encode_swap(123,100,MIN_SQRT,True,True)
        self.assertEqual(len(data),42)
        self.assertEqual(data[:8],DISC)
        self.assertEqual(int.from_bytes(data[8:16],"little"),123)
        self.assertEqual(int.from_bytes(data[16:24],"little"),100)
        self.assertEqual(data[-2:],bytes([1,1]))

    def test_bad_amount(self):
        with self.assertRaises(ValueError): encode_swap(0,0,MIN_SQRT)
        with self.assertRaises(ValueError): encode_swap(2**64,0,MIN_SQRT)

    def test_price_limit(self):
        with self.assertRaises(ValueError): encode_swap(1,0,0)
        self.assertEqual(len(encode_swap(1,0,MAX_SQRT,True,False)),42)

    def test_type_safety(self):
        with self.assertRaises(TypeError): encode_swap(1,0,MIN_SQRT,1,True)
