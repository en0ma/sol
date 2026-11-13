import base64
import unittest
from unittest.mock import patch
from arb.onchain_pool_discovery import VENUES, search_pair, verify
from arb.pumpswap_pool import PROGRAM, DISC
from arb.orca_whirlpool import b58


def pool_raw():
    raw=bytearray(261)
    raw[:8]=DISC
    for off,x in ((11,1),(43,2),(75,3),(107,4),(139,5),(171,6),(211,7)):
        raw[off:off+32]=bytes([x])*32
    return bytes(raw)


class PumpSwapDiscoveryTests(unittest.TestCase):
    @patch("arb.onchain_pool_discovery.call")
    def test_variable_length_pool_search_filters_mints(self, call):
        raw=pool_raw()
        a,b=b58(bytes([2])*32),b58(bytes([3])*32)
        call.side_effect=[[{"pubkey":"pool","account":{"owner":PROGRAM,
                       "executable":False,"data":[base64.b64encode(raw).decode(),"base64"]}}],[]]
        result=search_pair("rpc","pumpswap",a,b)
        self.assertEqual(list(result),["pool"])
        filters=call.call_args_list[0].args[2][1]["filters"]
        self.assertEqual(len(filters),2)
        self.assertEqual([f["memcmp"]["offset"] for f in filters],[43,75])
        self.assertEqual(len(VENUES),6)

    @patch("arb.onchain_pool_discovery.verify_pump")
    def test_verified_pumpswap_enters_graph_as_non_executable(self, verify_pump):
        verify_pump.return_value={"venue":"pumpswap","base_mint":"a","quote_mint":"b",
                                  "base_reserve":100,"quote_vault_balance":200,
                                  "fee_verified_onchain":False,"verified":True}
        p=verify("rpc","pumpswap","pool",{})
        self.assertEqual(p["mints"],["a","b"])
        self.assertEqual(p["vault_base_units"],[100,200])
        self.assertFalse(p["swap_simulated"])
        self.assertFalse(p["fee_verified_onchain"])
