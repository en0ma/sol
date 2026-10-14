import unittest,hashlib
from arb.raydium_clmm_swap import DISC,encode
class ClmmSwapV2Tests(unittest.TestCase):
    def test_discriminator_and_payload(self):
        self.assertEqual(DISC,hashlib.sha256(b"global:swap_v2").digest()[:8])
        data=encode(1000000,990000,0,True)
        self.assertEqual(len(data),41)
        self.assertEqual(int.from_bytes(data[8:16],"little"),1000000)
        self.assertEqual(int.from_bytes(data[16:24],"little"),990000)
        self.assertEqual(data[-1],1)
    def test_exact_output(self):
        data=encode(12000,150000,123456789,False)
        self.assertEqual(data[-1],0)
        self.assertEqual(int.from_bytes(data[24:40],"little"),123456789)
    def test_invalid_amounts(self):
        for x in (-1,0,1<<64,True):
            with self.assertRaises(ValueError):encode(x,1)
        with self.assertRaises(ValueError):encode(1,-1)
        with self.assertRaises(ValueError):encode(1,1,1<<128)
        with self.assertRaises(ValueError):encode(1,1,0,1)
