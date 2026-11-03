import unittest
from unittest.mock import patch
from arb.meteora_dlmm import decode,SIZE,DISC,swap_activation_evidence
from arb.onchain_pool_discovery import search_pair,MINTS
class MeteoraDlmmTests(unittest.TestCase):
    def fixture(self):
        data=bytearray(SIZE);data[:8]=DISC
        for i,offset in enumerate((88,120,152,184),1):
            data[offset:offset+32]=bytes([i])*32
        data[80:82]=(25).to_bytes(2,"little")
        return data
    def test_pool_identity(self):
        state=decode(bytes(self.fixture()))
        self.assertEqual(state["bin_step"],25)
        self.assertEqual(state["status"],0)
    def test_activation_offsets_match_authenticated_lbpair_layout(self):
        raw=self.fixture()
        raw[75]=1  # permission pool
        raw[86]=0  # activate by slot
        raw[816:824]=(1200).to_bytes(8,"little")
        raw[824:832]=(50).to_bytes(8,"little")
        state=decode(bytes(raw))
        self.assertEqual(state["pair_type"],1)
        self.assertEqual(state["activation_point"],1200)
        self.assertEqual(state["pre_activation_duration"],50)
        self.assertEqual(swap_activation_evidence(state,slot=1199,unix_timestamp=100)["reason"],
                         "ACTIVATION_PENDING_UNAUTHORIZED_SIGNER")
        self.assertTrue(swap_activation_evidence(state,slot=1200,
                                                  unix_timestamp=100)["swap_eligible"])
    def test_timestamp_activation_is_not_slot_activation(self):
        raw=self.fixture()
        raw[75]=2
        raw[86]=1
        raw[816:824]=(5000).to_bytes(8,"little")
        state=decode(bytes(raw))
        self.assertFalse(swap_activation_evidence(state,slot=90000,
                                                   unix_timestamp=4999)["swap_eligible"])
        self.assertTrue(swap_activation_evidence(state,slot=1,
                                                  unix_timestamp=5000)["swap_eligible"])
    def test_permissionless_enabled_and_disabled(self):
        raw=self.fixture()
        raw[75]=0
        raw[816:824]=(2**60).to_bytes(8,"little")
        state=decode(bytes(raw))
        self.assertTrue(swap_activation_evidence(state,slot=12,unix_timestamp=34)["swap_eligible"])
        state["status"]=1
        self.assertFalse(swap_activation_evidence(state,slot=12,unix_timestamp=34)["swap_eligible"])
    def test_unsupported_activation_fails_closed(self):
        state=decode(bytes(self.fixture()))
        state["activation_type"]=5
        with self.assertRaises(ValueError):
            swap_activation_evidence(state,slot=123,unix_timestamp=123)
    def test_bad_discriminator(self):
        with self.assertRaises(ValueError):decode(bytes(SIZE))
    @patch("arb.onchain_pool_discovery.call",return_value=[])
    def test_filtered_mint_offsets(self,call):
        search_pair("rpc","meteora_dlmm",MINTS["WSOL"],MINTS["USDT"])
        filters=call.call_args_list[0].args[2][1]["filters"]
        self.assertEqual([x["memcmp"]["offset"] for x in filters[1:]],[88,120])
