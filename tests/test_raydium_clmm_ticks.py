import unittest
from arb.raydium_clmm_ticks import start_tick,SIZE
class ClmmTickTests(unittest.TestCase):
    def test_negative_floor(self):
        self.assertEqual(start_tick(-1,10),-600)
        self.assertEqual(start_tick(-600,10),-600)
        self.assertEqual(start_tick(601,10),600)
    def test_layout_size(self):
        self.assertEqual(SIZE,8+32+4+168*60+1+115)
    def test_validation(self):
        for spacing in (0,-1,32768):
            with self.assertRaises(ValueError):start_tick(3,spacing)
