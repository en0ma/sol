import unittest
from arb.raydium_clmm import SIZE,DISC,decode
class RaydiumClmmTests(unittest.TestCase):
    def fixture(self):
        b=bytearray(SIZE);b[:8]=DISC
        for i,offset in enumerate((9,41,73,105,137,169,201),1):
            b[offset:offset+32]=bytes([i])*32
        b[235:237]=(16).to_bytes(2,"little")
        b[237:253]=(1000000).to_bytes(16,"little")
        b[253:269]=(1<<64).to_bytes(16,"little")
        return b
    def test_layout_and_offsets(self):
        s=decode(bytes(self.fixture()))
        self.assertEqual(s["tick_spacing"],16)
        self.assertEqual(s["liquidity"],1000000)
        self.assertEqual(s["sqrt_price_x64"],1<<64)
    def test_rejects_bad_layout(self):
        with self.assertRaises(ValueError):decode(bytes(SIZE))
    def test_rejects_invalid_price(self):
        b=self.fixture();b[253:269]=bytes(16)
        with self.assertRaises(ValueError):decode(bytes(b))

class SourceFeeSideTests(RaydiumClmmTests):
    def test_real_pool_enum_selects_input_vs_output_by_direction(self):
        from arb.raydium_clmm import fee_collected_from_input,fee_collection_source_evidence
        for fee_on,expected in ((0,(True,True)),(1,(True,False)),(2,(False,True))):
            with self.subTest(fee_on=fee_on):
                raw=self.fixture()
                raw[390]=fee_on
                pool=decode(bytes(raw))
                m0,m1=pool["token_mint_0"],pool["token_mint_1"]
                actual=(fee_collected_from_input(pool,m0),
                        fee_collected_from_input(pool,m1))
                self.assertEqual(actual,expected)
                evidence=fee_collection_source_evidence(pool,m0)
                self.assertEqual(evidence["fee_on_input"],expected[0])
                self.assertTrue(evidence["source_pool_fee_side_decoded"])
                self.assertFalse(evidence["protocol_exact_quote_verified"])

    def test_disabled_swap_bit_rejected_at_source_decode(self):
        raw=self.fixture()
        raw[389]=1<<4
        with self.assertRaisesRegex(ValueError,"swap disabled"):
            decode(bytes(raw))

    def test_unsupported_fee_enum_fails_closed(self):
        raw=self.fixture()
        raw[390]=3
        with self.assertRaisesRegex(ValueError,"fee collection mode"):
            decode(bytes(raw))
