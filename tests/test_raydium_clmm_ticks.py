import unittest
from arb.raydium_clmm_ticks import start_tick,SIZE,initialized_tick_starts,POOL_BITMAP_OFFSET
class ClmmTickTests(unittest.TestCase):
    def test_negative_floor(self):
        self.assertEqual(start_tick(-1,10),-600)
        self.assertEqual(start_tick(-600,10),-600)
        self.assertEqual(start_tick(601,10),600)
    def test_layout_size(self):
        self.assertEqual(SIZE,8+32+4+168*60+1+115)
    def test_initialized_bitmap_skips_noninitialized_current_array(self):
        raw=bytearray(1544)
        # tick_spacing=10 -> span=600; current tick=125 -> index 0
        # Current array (bitmap bit 512) is absent. Initialized arrays: -600,-1200,+600.
        for tick_start in (-1200,-600,600):
            bit=tick_start//600+512
            byte=POOL_BITMAP_OFFSET+bit//8
            raw[byte]|=1<<(bit%8)
        self.assertEqual(initialized_tick_starts(raw,125,10,True),
                         [-600,-1200])
        self.assertEqual(initialized_tick_starts(raw,125,10,False),
                         [600])
        with self.assertRaises(ValueError):
            initialized_tick_starts(bytes(1544),125,10,True)
    def test_bitmap_default_range_fail_closed(self):
        with self.assertRaises(ValueError):
            initialized_tick_starts(bytes(1544),400000,1,True)
    def test_validation(self):
        for spacing in (0,-1,32768):
            with self.assertRaises(ValueError):start_tick(3,spacing)
