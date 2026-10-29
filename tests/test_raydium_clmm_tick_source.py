"""Raydium CLMM authenticated tick data must match official packed account bytes."""
import hashlib,unittest
from unittest.mock import patch
from solders.pubkey import Pubkey
from arb.raydium_clmm import PROGRAM
from arb.raydium_clmm_tick_source import (
    TICK_ARRAY_LEN,TICK_STATE_LEN,DISC,array_start,tick_array_pda,
    decode_tick_array,capture_tick_arrays)

POOL="61R1ndXxvsWXXkWSyNkCxnzwd3zUNB8Q2ibmkiLPC8ht"

def tick_blob(start,spacing):
    b=bytearray(TICK_ARRAY_LEN)
    b[:8]=DISC
    b[8:40]=bytes(Pubkey.from_string(POOL))
    b[40:44]=start.to_bytes(4,"little",signed=True)
    off=44+4*TICK_STATE_LEN
    b[off:off+4]=(start+4*spacing).to_bytes(4,"little",signed=True)
    b[off+4:off+20]=(-500).to_bytes(16,"little",signed=True)
    b[off+20:off+36]=(1000).to_bytes(16,"little")
    b[44+60*TICK_STATE_LEN]=1
    return bytes(b)

class RaydiumTickAuthenticationTests(unittest.TestCase):
    def test_negative_floor_start_index(self):
        self.assertEqual(array_start(-1,60),-3600)
        self.assertEqual(array_start(0,60),0)
        self.assertEqual(array_start(3600,60),3600)
    def test_real_pda_not_arbitrary_address(self):
        self.assertEqual(tick_array_pda(POOL,0),tick_array_pda(POOL,0))
        self.assertNotEqual(tick_array_pda(POOL,0),tick_array_pda(POOL,3600))
    def test_exact_packed_array_initialized_liquidity(self):
        row=decode_tick_array(tick_blob(0,60),POOL,0,60)
        self.assertEqual(row["initialized_tick_count"],1)
        self.assertEqual(row["initialized_ticks"][0]["tick"],240)
        self.assertEqual(row["initialized_ticks"][0]["liquidity_net"],"-500")
    def test_wrong_pool_rejected(self):
        with self.assertRaisesRegex(ValueError,"pool or index"):
            decode_tick_array(tick_blob(0,60),str(Pubkey.new_unique()),0,60)
    def test_tick_count_forgery_rejected(self):
        b=bytearray(tick_blob(0,60))
        b[44+60*TICK_STATE_LEN]=2
        with self.assertRaisesRegex(ValueError,"initialized tick count"):
            decode_tick_array(bytes(b),POOL,0,60)
    def test_wrong_layout_rejected(self):
        with self.assertRaisesRegex(ValueError,"discriminator or length"):
            decode_tick_array(b"garbage",POOL,0,60)
    def test_non_positive_liquidity_rejected_before_rpc(self):
        with patch("arb.raydium_clmm_tick_source.call") as rpc:
            with self.assertRaisesRegex(ValueError,"verified pool"):
                capture_tick_arrays("https://readonly.example",POOL,
                    {"liquidity":0,"tick_current":0,"tick_spacing":60})
            rpc.assert_not_called()
    def test_out_of_range_radius_rejected(self):
        with self.assertRaisesRegex(ValueError,"bounded"):
            capture_tick_arrays("https://readonly.example",POOL,
                {"liquidity":100,"tick_current":0,"tick_spacing":60},radius=20)

if __name__=="__main__":unittest.main()
