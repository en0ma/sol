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
            raw[pos+4:pos+20]=(-20 if i==3 else 20).to_bytes(16,"little",signed=True)
            raw[pos+20:pos+36]=(100).to_bytes(16,"little")
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

    def test_real_raydium_zeroed_uninitialized_tick_slots(self):
        raw=self.fixture()
        # Real source array JkVJo8v3y38hDjciDxSyauz8JvY1KrFLU9xA4Z9ieJk
        # has zero-valued indexes in unused slots while populated slots
        # are strictly aligned. Preserve a real-account decoding property.
        for i in range(60):
            if i not in (3,7):
                raw[44+i*168:48+i*168]=b"\\x00"*4
        ticks=initialized_ticks(bytes(raw),0,10)
        self.assertEqual([t["tick_index"] for t in ticks],[30,70])
    def test_populated_wrong_index_cannot_be_normalized(self):
        raw=self.fixture()
        pos=44+3*168
        raw[pos:pos+4]=(999).to_bytes(4,"little",signed=True)
        with self.assertRaisesRegex(ValueError,"initialized .*index"):
            initialized_ticks(bytes(raw),0,10)

    def test_malformed_tick_index_rejected(self):
        raw=self.fixture()
        raw[44+5*168:48+5*168]=(500).to_bytes(4,"little",signed=True)
        with self.assertRaisesRegex(ValueError,"forged index"):
            initialized_ticks(bytes(raw),0,10)
