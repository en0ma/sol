import unittest
from arb.pumpswap_global_config import decode, DISC, MIN_SIZE
from arb.pumpswap_pool import decode as decode_pool, DISC as POOL_DISC


class PumpSwapFeeAccountTests(unittest.TestCase):
    def test_global_config_fee_and_swap_flags(self):
        raw=bytearray(MIN_SIZE)
        raw[:8]=DISC
        raw[40:48]=(20).to_bytes(8,"little")
        raw[48:56]=(5).to_bytes(8,"little")
        raw[56]=16
        raw[313:321]=(5).to_bytes(8,"little")
        data=decode(bytes(raw))
        self.assertEqual(data["lp_fee_bps"],20)
        self.assertTrue(data["buy_enabled"])
        self.assertFalse(data["sell_enabled"])
        self.assertFalse(data["effective_fee_verified"])
        raw[48:56]=(10001).to_bytes(8,"little")
        with self.assertRaises(ValueError):
            decode(bytes(raw))

    def test_pool_fee_buckets_and_partial_extensions(self):
        raw=bytearray(287)
        raw[:8]=POOL_DISC
        for off,val in ((11,1),(43,2),(75,3),(107,4),
                        (139,5),(171,6),(211,7)):
            raw[off:off+32]=bytes([val])*32
        raw[271:279]=(120).to_bytes(8,"little")
        raw[279:287]=(40).to_bytes(8,"little")
        p=decode_pool(bytes(raw))
        self.assertEqual(p["protocol_fees"],120)
        self.assertEqual(p["creator_fees"],40)
        self.assertIsNone(decode_pool(bytes(raw[:271]))["protocol_fees"])
        with self.assertRaisesRegex(ValueError,"partial"):
            decode_pool(bytes(raw[:275]))
