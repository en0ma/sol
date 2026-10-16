import unittest
from arb.raydium_clmm_tick_decode import initialized_ticks,next_boundary
from arb.raydium_clmm_ticks import DISC,SIZE


class ClmmTickDecodeTests(unittest.TestCase):
    def fixture(self):
        raw=bytearray(SIZE)
        raw[:8]=DISC
        raw[40:44]=(0).to_bytes(4,"little",signed=True)
        for i in range(60):
            pos=44+i*168
            raw[pos:pos+4]=(i*10).to_bytes(4,"little",signed=True)
        for i in (3,7):
            pos=44+i*168
            raw[pos+4:pos+20]=(100).to_bytes(16,"little")
            raw[pos+20:pos+36]=(-20 if i==3 else 20).to_bytes(16,"little",signed=True)
        return raw

    def test_decodes_and_selects_directional_boundaries(self):
        ticks=initialized_ticks(bytes(self.fixture()),0,10)
        self.assertEqual(len(ticks),2)
        self.assertEqual(next_boundary(ticks,45,True),30)
        self.assertEqual(next_boundary(ticks,45,False),70)

    def test_missing_boundary_rejected(self):
        ticks=initialized_ticks(bytes(self.fixture()),0,10)
        with self.assertRaisesRegex(ValueError,"outside"):
            next_boundary(ticks,90,False)

    def test_malformed_tick_index_rejected(self):
        raw=self.fixture()
        raw[44+5*168:48+5*168]=(500).to_bytes(4,"little",signed=True)
        with self.assertRaisesRegex(ValueError,"index layout"):
            initialized_ticks(bytes(raw),0,10)
