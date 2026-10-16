import unittest
from unittest.mock import patch
from arb.whirlpool_ticks import start_tick, candidate_starts, decode_fixed_ticks, nearest_observed_ticks, DISC, FIXED_LEN, TICK_HEADER, TICK_SIZE
class TickMathTests(unittest.TestCase):
    def test_negative_floor(self):
        self.assertEqual(start_tick(-1,8),-704)
        self.assertEqual(start_tick(703,8),0)
        self.assertEqual(start_tick(704,8),704)
    def test_five_neighbor_starts(self):
        self.assertEqual(candidate_starts(5,8),[0,704,1408,-704,-1408])
    def test_invalid_spacing(self):
        with self.assertRaises(ValueError): start_tick(0,0)

class FixedArrayDecodeTests(unittest.TestCase):
    def fixture(self, *, flag=1, gross=100, net=-20):
        raw=bytearray(FIXED_LEN)
        raw[:8]=DISC
        raw[8:12]=(0).to_bytes(4,"little",signed=True)
        raw[TICK_HEADER]=flag
        raw[TICK_HEADER+1:TICK_HEADER+17]=net.to_bytes(16,"little",signed=True)
        raw[TICK_HEADER+17:TICK_HEADER+33]=gross.to_bytes(16,"little")
        raw[-32:]=bytes([2])*32
        return bytes(raw)

    @patch("arb.whirlpool_ticks.b58",return_value="expected-pool")
    def test_initialized_tick_decoded(self,_):
        ticks=decode_fixed_ticks(self.fixture(),"expected-pool",0,8)
        self.assertEqual(ticks,[{"tick_index":0,"liquidity_net":"-20","liquidity_gross":"100"}])

    @patch("arb.whirlpool_ticks.b58",return_value="expected-pool")
    def test_corrupt_flags_and_liquidity_fail_closed(self,_):
        for raw in (self.fixture(flag=2),self.fixture(gross=0),
                    self.fixture(gross=1,net=-20),self.fixture()[:-1]):
            with self.subTest(length=len(raw)):
                with self.assertRaises(ValueError):
                    decode_fixed_ticks(raw,"expected-pool",0,8)

    @patch("arb.whirlpool_ticks.b58",return_value="expected-pool")
    def test_wrong_identity_rejected(self,_):
        with self.assertRaises(ValueError):
            decode_fixed_ticks(self.fixture(),"other-pool",0,8)
        with self.assertRaises(ValueError):
            decode_fixed_ticks(self.fixture(),"expected-pool",88,8)

class ObservedTickCoverageTests(unittest.TestCase):
    def test_nearest_across_arrays_not_just_current_array(self):
        entries=[
            {"start_tick":0,"status":"FIXED_VALID","ticks":[
                {"tick_index":8},{"tick_index":24}]},
            {"start_tick":704,"status":"FIXED_VALID","ticks":[
                {"tick_index":704},{"tick_index":720}]},
            {"start_tick":-704,"status":"MISSING"}]
        result=nearest_observed_ticks(entries,700,8)
        self.assertEqual(result["nearest_initialized_below"],24)
        self.assertEqual(result["nearest_initialized_above"],704)
        self.assertEqual(result["arrays_valid"],2)
        self.assertEqual(result["initialized_ticks_observed"],4)
        self.assertFalse(result["complete_liquidity_path"])
        self.assertFalse(result["executable_quote"])

    def test_fail_closed_on_invalid_tick_metadata(self):
        invalid=[
            [{"start_tick":0,"status":"FIXED_VALID","ticks":[{"tick_index":3}]}],
            [{"start_tick":0,"status":"FIXED_VALID","ticks":[{"tick_index":704}]}],
            [{"start_tick":1,"status":"FIXED_VALID","ticks":[]}],
            [{"start_tick":0,"status":"FIXED_VALID","ticks":[]},
             {"start_tick":0,"status":"MISSING"}]]
        for entries in invalid:
            with self.subTest(entries=entries):
                with self.assertRaises(ValueError):
                    nearest_observed_ticks(entries,10,8)
