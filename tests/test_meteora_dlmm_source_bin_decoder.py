import unittest
from unittest.mock import patch
from arb.meteora_dlmm_source_bin_decoder import (
    decode_bin_array,directional_bins,EXPECTED_SIZE,BIN_START,BIN_SIZE
)
from arb.meteora_dlmm_bin_preflight import BIN_ARRAY_DISC

POOL="11111111111111111111111111111111"
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
class SourceBinDecoderTests(unittest.TestCase):
    def account(self,index=0):
        raw=bytearray(EXPECTED_SIZE)
        raw[:8]=BIN_ARRAY_DISC
        raw[8:16]=index.to_bytes(8,"little",signed=True)
        raw[16]=1
        raw[24:56]=bytes(32)
        off=BIN_START+15*BIN_SIZE
        raw[off:off+8]=(123).to_bytes(8,"little")
        raw[off+8:off+16]=(456).to_bytes(8,"little")
        raw[off+16:off+32]=(1<<64).to_bytes(16,"little")
        raw[off+32:off+48]=(789).to_bytes(16,"little")
        return raw
    def test_real_borsh_bin_layout_yields_liquidity(self):
        result=decode_bin_array(bytes(self.account()),pool=POOL,index=0)
        self.assertEqual(result["bin_count"],70)
        bin15=result["bins"][15]
        self.assertEqual(bin15["bin_id"],15)
        self.assertEqual(bin15["amount_x"],123)
        self.assertEqual(bin15["amount_y"],456)
        self.assertEqual(bin15["price_q64"],1<<64)
        self.assertEqual(bin15["liquidity_supply"],789)
        self.assertFalse(result["protocol_exact_verified"])
    def test_negative_array_index_preserves_bin_ids(self):
        result=decode_bin_array(bytes(self.account(-1)),pool=POOL,index=-1)
        self.assertEqual(result["bins"][0]["bin_id"],-70)
        self.assertEqual(result["bins"][69]["bin_id"],-1)
    def test_wrong_length_disc_pool_or_index_fail_closed(self):
        raw=self.account()
        variants=[bytes(raw[:-1]),b"x"*EXPECTED_SIZE,bytes(raw)]
        for data in variants[:2]:
            with self.assertRaises(ValueError):
                decode_bin_array(data,pool=POOL,index=0)
        with self.assertRaisesRegex(ValueError,"index"):
            decode_bin_array(bytes(raw),pool=POOL,index=1)
        with self.assertRaisesRegex(ValueError,"parent"):
            decode_bin_array(bytes(raw),pool="So11111111111111111111111111111111111111112",index=0)
    def test_funded_bin_without_price_or_supply_refused(self):
        raw=self.account()
        off=BIN_START+15*BIN_SIZE
        raw[off+16:off+32]=bytes(16)
        with self.assertRaisesRegex(ValueError,"zero price"):
            decode_bin_array(bytes(raw),pool=POOL,index=0)
    def test_source_array_bin_walk_does_not_invent_fees(self):
        decoded=decode_bin_array(bytes(self.account()),pool=POOL,index=0)
        b={"bins":decoded["bins"],"source_account_verified":True,**SAFE}
        walk=directional_bins([b],active_id=15,x_to_y=True)
        self.assertEqual(walk["bins"][0]["amount_y"],456)
        self.assertFalse(walk["dynamic_fee_verified"])
        self.assertFalse(walk["protocol_exact_verified"])
    def test_rejects_unauthenticated_array_walk(self):
        decoded=decode_bin_array(bytes(self.account()),pool=POOL,index=0)
        with self.assertRaisesRegex(ValueError,"source-authenticated"):
            directional_bins([decoded],active_id=15,x_to_y=False)

    def test_actual_source_internal_bitmap_and_extension_boundaries(self):
        from arb.meteora_dlmm_source_bin_decoder import bitmap_initialized
        from arb.meteora_dlmm import DISC,SIZE
        from arb.meteora_dlmm_bin_preflight import BITMAP_EXTENSION_DISC,BITMAP_EXTENSION_SIZE
        raw=bytearray(SIZE);raw[:8]=DISC
        # Actual source artifact 15263237974 / source-170.json, slot 474953745.
        initialized=(-8,-7,-6,-5,-4,0)
        raw[584:712]=sum(1<<(i+512) for i in initialized).to_bytes(128,"little")
        self.assertEqual([i for i in range(-8,2) if bitmap_initialized(bytes(raw),i)],list(initialized))
        self.assertIsNone(bitmap_initialized(bytes(raw),512))
        ext=bytearray(BITMAP_EXTENSION_SIZE);ext[:8]=BITMAP_EXTENSION_DISC
        ext[40]=1;ext[808]=2
        self.assertTrue(bitmap_initialized(bytes(raw),512,extension_raw=bytes(ext)))
        self.assertTrue(bitmap_initialized(bytes(raw),-514,extension_raw=bytes(ext)))
        self.assertFalse(bitmap_initialized(bytes(raw),-513,extension_raw=bytes(ext)))
        self.assertIsNone(bitmap_initialized(bytes(raw),6656,extension_raw=bytes(ext)))

    def test_fee_schedule_allows_only_whole_verified_empty_array_gaps(self):
        from arb.meteora_dlmm_source_fee_decoder import dynamic_fee_rate_by_bin
        from arb.meteora_dlmm import DISC,SIZE
        raw=bytearray(SIZE);raw[:8]=DISC
        kwargs=dict(bin_step=25,observed_unix=123,active_bin_id=-211,
                    visited_bin_ids=[-211,0],swap_x_for_y=False)
        with self.assertRaisesRegex(ValueError,"contiguous"):
            dynamic_fee_rate_by_bin(bytes(raw),**kwargs)
        with self.assertRaisesRegex(ValueError,"contiguous"):
            dynamic_fee_rate_by_bin(bytes(raw),verified_empty_arrays=[-3,-1],**kwargs)
        result=dynamic_fee_rate_by_bin(bytes(raw),verified_empty_arrays=[-3,-2,-1],**kwargs)
        self.assertEqual([x["bin_id"] for x in result["rates"]],[-211,0])
        self.assertFalse(result["protocol_exact_verified"])
if __name__=="__main__":unittest.main()
