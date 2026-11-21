"""Authenticated permissioned DLMM offline Clock gate regressions."""
import base64
import unittest
from unittest.mock import patch
from arb.dlmm_offline_clock import permissioned_dlmm_slot_requirement, align_permissioned_dlmm_clock
from arb.meteora_dlmm import DISC,SIZE,PROGRAM

POOL="3msVd34R5KxonDzyNSV5nT19UtUeJ2RF1NaQhvVPNLxL"

def fixture(*,pair_type=1,activation_type=0,activation_point=100,source_slot=200):
    raw=bytearray(SIZE)
    raw[:8]=DISC
    for i,offset in enumerate((88,120,152,184),1):
        raw[offset:offset+32]=bytes([i])*32
    raw[75]=pair_type
    raw[86]=activation_type
    raw[80:82]=(25).to_bytes(2,"little")
    raw[816:824]=activation_point.to_bytes(8,"little")
    return {"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
            "fixture_kind":"AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE",
            "route_venues":["meteora_dlmm","orca","raydium_cpmm"],
            "route_pool_addresses":[POOL,"orca-pool","cpmm-pool"],
            "accounts":{POOL:{"owner":PROGRAM,"data":[base64.b64encode(raw).decode(),"base64"]}},
            "state_accounts_observed_slot":source_slot,
            "actionable":False,"live_execution_approved":False,"broadcast":False}

class OfflineClockTests(unittest.TestCase):
    def test_rejects_future_or_non_slot_permissioned_pool(self):
        with self.assertRaisesRegex(ValueError,"predates"):
            permissioned_dlmm_slot_requirement(fixture(source_slot=99))
        with self.assertRaisesRegex(ValueError,"non-slot"):
            permissioned_dlmm_slot_requirement(fixture(activation_type=1))
    def test_nonpermissioned_does_not_need_alignment(self):
        self.assertEqual(permissioned_dlmm_slot_requirement(fixture(pair_type=0)),(200,[]))
    @patch("arb.source_snapshot_manifest.verify",return_value=True)
    @patch("arb.next_ten_fork_pool_probe.source_clock")
    @patch("arb.dlmm_offline_clock.call")
    def test_forward_only_and_readback(self,rpc,read_clock,verify):
        read_clock.side_effect=[{"slot":2,"unix_timestamp":1},
                                {"slot":200,"unix_timestamp":2}]
        with patch("arb.dlmm_offline_clock.source_clock",side_effect=read_clock.side_effect):
            evidence=align_permissioned_dlmm_clock("http://127.0.0.1:8899",fixture())
        rpc.assert_called_once_with("http://127.0.0.1:8899",
                                    "surfnet_timeTravel",[{"absoluteSlot":200}])
        self.assertEqual(evidence["status"],"PERMISSIONED_DLMM_SOURCE_SLOT_ALIGNMENT_VERIFIED")
        self.assertFalse(evidence["source_clock_timestamp_parity_claimed"])
    @patch("arb.source_snapshot_manifest.verify",return_value=True)
    @patch("arb.dlmm_offline_clock.source_clock",
           side_effect=[{"slot":2,"unix_timestamp":1},{"slot":3,"unix_timestamp":2}])
    @patch("arb.dlmm_offline_clock.call")
    def test_rejects_failed_clock_warp(self,rpc,read_clock,verify):
        with self.assertRaisesRegex(ValueError,"alignment failed"):
            align_permissioned_dlmm_clock("http://127.0.0.1:8899",fixture())

if __name__=="__main__":
    unittest.main()
