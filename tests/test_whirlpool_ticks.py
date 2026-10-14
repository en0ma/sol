import unittest
from arb.whirlpool_ticks import start_tick, candidate_starts
class TickMathTests(unittest.TestCase):
    def test_negative_floor(self):
        self.assertEqual(start_tick(-1,8),-704)
        self.assertEqual(start_tick(703,8),0)
        self.assertEqual(start_tick(704,8),704)
    def test_five_neighbor_starts(self):
        self.assertEqual(candidate_starts(5,8),[0,704,1408,-704,-1408])
    def test_invalid_spacing(self):
        with self.assertRaises(ValueError): start_tick(0,0)
