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

    def test_official_extension_positive_negative_word_order(self):
        from arb.raydium_clmm_ticks import bitmap_bit,extended_tick_starts
        from arb.raydium_clmm_bitmap_extension_source import LENGTH,DISC
        ext=bytearray(LENGTH);ext[:8]=DISC
        # Positive array 512 starts at word zero; negative -513 is high bit.
        ext[40]=1;ext[40+14*64+63]=128;ext[40+14*64+64]=1
        ext=bytes(ext);default=bytes(128)
        self.assertTrue(bitmap_bit(default,512,ext))
        self.assertTrue(bitmap_bit(default,-513,ext))
        self.assertTrue(bitmap_bit(default,-1536,ext))
        self.assertFalse(bitmap_bit(default,-514,ext))
        self.assertEqual(extended_tick_starts(bytes(1544),ext,-30780,1,True,arrays=2),[-30780,-92160])
        with self.assertRaisesRegex(ValueError,"extension required"):
            bitmap_bit(default,-513)
