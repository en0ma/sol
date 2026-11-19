"""Raydium CPMM direct-PDA discovery never counts unoccupied or unverified pools."""
import base64
import unittest
from unittest.mock import patch
from arb.raydium_cpmm_pda_bridge import discover,source_config_addresses
from arb.raydium_cpmm import PROGRAM
from arb.orca_whirlpool import SOL,USDC

RPC="http://127.0.0.1:8899"
CONFIG=SOL

class CPMMDirectPdaTests(unittest.TestCase):
    def test_source_config_requires_owner_and_onchain_decoded_pool(self):
        valid=base64.b64encode(b"pool-bytes").decode()
        rows=[{"venue":"raydium_cpmm","address":"a"},
              {"venue":"raydium_cpmm","address":"b"}]
        def read(rpc,method,params):
            self.assertEqual(method,"getMultipleAccounts")
            self.assertEqual(params[0],["a","b"])
            return {"value":[
                {"owner":PROGRAM,"executable":False,
                 "data":[valid,"base64"]},
                {"owner":"wrong-owner","executable":False,
                 "data":[valid,"base64"]}]}
        with patch("arb.raydium_cpmm_pda_bridge.decode",
                   return_value={"amm_config":CONFIG}):
            self.assertEqual(source_config_addresses(
                RPC,rows,call_fn=read),[CONFIG])

    def test_unoccupied_derived_pda_is_never_a_pool(self):
        calls=[]
        def read(rpc,method,params):
            calls.append((rpc,method,params[0]))
            return {"value":[None]*len(params[0])}
        with patch("arb.raydium_cpmm_pda_bridge.local_rpc_only"):
            report=discover(RPC,[],[(SOL,USDC)],
                            config_fn=lambda *_:[CONFIG],call_fn=read)
        self.assertEqual(report["candidate_pdas_checked"],1)
        self.assertEqual(report["verified_new_pool_count"],0)
        self.assertEqual(report["source_verified_new_pools"],[])
        self.assertFalse(report["broadcast"])

    def test_real_source_verification_required_and_identity_matches(self):
        raw=base64.b64encode(b"pool-bytes").decode()
        calls=[]
        def read(rpc,method,params):
            calls.append((method,params[0]))
            return {"value":[{"owner":PROGRAM,"executable":False,
                               "data":[raw,"base64"]} for _ in params[0]]}
        def verify_source(rpc,venue,address,state):
            self.assertEqual((rpc,venue),(RPC,"raydium_cpmm"))
            self.assertEqual(state["token_0_mint"],SOL)
            self.assertEqual(state["token_1_mint"],USDC)
            return {"venue":venue,"address":address,"mints":[SOL,USDC],
                    "slot":99,"swap_simulated":False}
        with patch("arb.raydium_cpmm_pda_bridge.local_rpc_only"),patch(
                "arb.raydium_cpmm_pda_bridge.decode",return_value={
                    "token_0_mint":SOL,"token_1_mint":USDC}):
            good=discover(RPC,[],[(SOL,USDC)],
                          config_fn=lambda *_:[CONFIG],
                          call_fn=read,verify_fn=verify_source)
            self.assertEqual(good["verified_new_pool_count"],1)
            self.assertTrue(good["source_verified_new_pools"][0]["source_verified_only"])
            bad=discover(RPC,[],[(SOL,USDC)],
                         config_fn=lambda *_:[CONFIG],call_fn=read,
                         verify_fn=lambda rpc,venue,address,state:{
                             "venue":venue,"address":address,"mints":[SOL,"wrong"],
                             "slot":99,"swap_simulated":False})
        self.assertEqual(bad["verified_new_pool_count"],0)
        self.assertEqual(len(bad["errors"]),1)
        self.assertFalse(bad["actionable"])

    def test_refuses_incomplete_snapshot_and_invalid_search_budget(self):
        with patch("arb.raydium_cpmm_pda_bridge.local_rpc_only"):
            with self.assertRaises(ValueError):
                discover(RPC,[],[(SOL,USDC)],maximum_pairs=0)
            with self.assertRaises(ValueError):
                discover(RPC,[],[(SOL,USDC)],
                         config_fn=lambda *_:[CONFIG],
                         call_fn=lambda *_args:{"value":[]})

if __name__=="__main__":
    unittest.main()
