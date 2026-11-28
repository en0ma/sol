import unittest
from arb.pumpswap_fee_config import DISC, decode


def encode_fees(a,b,c):
    return b"".join(x.to_bytes(8,"little") for x in (a,b,c))


def sample():
    return (DISC + bytes([4]) + bytes([7])*32 + encode_fees(20,5,5)
            + (2).to_bytes(4,"little")
            + (100).to_bytes(16,"little") + encode_fees(100,20,10)
            + (1000).to_bytes(16,"little") + encode_fees(50,10,5)
            + (1).to_bytes(4,"little")
            + (200).to_bytes(16,"little") + encode_fees(25,5,5)
            + encode_fees(30,10,5))


class PumpFeeConfigTests(unittest.TestCase):
    def test_parse_all_fee_variants(self):
        result=decode(sample())
        self.assertEqual(result["flat_fees"]["lp_fee_bps"],20)
        self.assertEqual(result["fee_tiers"][1]["market_cap_threshold"],1000)
        self.assertEqual(result["stable_fee_tiers"][0]["fees"]["lp_fee_bps"],25)
        self.assertEqual(result["exotic_flat_fees"]["creator_fee_bps"],5)
        self.assertFalse(result["account_authenticated"])
        self.assertFalse(result["effective_fee_verified"])

    def test_truncated_and_invalid_tiers_fail_closed(self):
        raw=sample()
        for candidate in (raw[:60],raw[:-8],bytes(len(raw)), raw+b"\x01"):
            with self.subTest(length=len(candidate)):
                with self.assertRaises(ValueError):
                    decode(candidate)
        malformed=bytearray(raw)
        malformed[65:69]=(65).to_bytes(4,"little")
        with self.assertRaises(ValueError):
            decode(bytes(malformed))
