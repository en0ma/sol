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

if __name__=="__main__":unittest.main()
