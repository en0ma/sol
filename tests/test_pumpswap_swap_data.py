import unittest
from arb.pumpswap_swap_data import (encode_sell,encode_buy_exact_quote_in,
                                     SELL_DISC,BUY_EXACT_QUOTE_IN_DISC)


class PumpSwapSwapDataTests(unittest.TestCase):
    def test_sell_exact_input_layout(self):
        data=encode_sell(12000,500)
        self.assertEqual(data[:8],SELL_DISC)
        self.assertEqual(len(data),24)
        self.assertEqual(int.from_bytes(data[8:16],"little"),12000)
        self.assertEqual(int.from_bytes(data[16:24],"little"),500)

    def test_buy_exact_quote_input_option_bool(self):
        for flag,suffix in ((None,b"\x00"),(False,b"\x01\x00"),(True,b"\x01\x01")):
            data=encode_buy_exact_quote_in(12000,500,track_volume=flag)
            self.assertEqual(data[:8],BUY_EXACT_QUOTE_IN_DISC)
            self.assertEqual(data[24:],suffix)

    def test_invalid_input_and_slippage_fail_closed(self):
        for bad in (0,-1,1<<64,True,1.2):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    encode_sell(bad,1)
        with self.assertRaises(ValueError):
            encode_buy_exact_quote_in(100,1,track_volume="yes")
