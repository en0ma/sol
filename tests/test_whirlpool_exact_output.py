import unittest
from arb.whirlpool_swap import encode_swap, MIN_SQRT
class ExactOutputTests(unittest.TestCase):
    def test_exact_output_flag_and_maximum_input(self):
        data=encode_swap(10000,1000000,MIN_SQRT,False,True)
        self.assertEqual(data[-2:],bytes([0,1]))
        self.assertEqual(int.from_bytes(data[8:16],"little"),10000)
        self.assertEqual(int.from_bytes(data[16:24],"little"),1000000)
