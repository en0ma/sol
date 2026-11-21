import unittest
from unittest.mock import patch
from arb.raydium_cpmm import decode,SIZE,DISC
class Tests(unittest.TestCase):
    @patch("arb.raydium_cpmm.b58",side_effect=lambda v:v.hex())
    def test_creator_fee_mode_and_enable_are_decoded_from_pool_bytes(self,_):
        b=bytearray(SIZE);b[:8]=DISC
        for i in range(10):b[8+i*32:40+i*32]=bytes([i+1])*32
        b[389]=2;b[390]=1
        s=decode(bytes(b))
        self.assertEqual(s["creator_fee_on"],2)
        self.assertTrue(s["enable_creator_fee"])
        b[389]=3
        with self.assertRaises(ValueError):decode(bytes(b))
if __name__=="__main__":unittest.main()
