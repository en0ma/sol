"""DLMM source windows never manufacture or reorder remaining bin-array accounts."""
import base64
import unittest
from unittest.mock import patch
from solders.pubkey import Pubkey
from arb.meteora_dlmm import PROGRAM
from arb.meteora_dlmm_bin_preflight import (
    BIN_ARRAY_DISC,bin_array_pda,inspect_directional_bin_arrays)
from arb.meteora_dlmm_swap import build_swap


class DlmmDirectionalWindows(unittest.TestCase):
    def setUp(self):
        self.pool=str(Pubkey.new_unique())
        self.active=-171
        self.accounts=[str(Pubkey.new_unique()) for _ in range(8)]
        self.index_to_key={
            self.active-i:bin_array_pda(self.pool,self.active-i)
            for i in range(8)}
        self.fake_account=self.pool

    def source(self,index, *, owner=PROGRAM, parent=None):
        raw=bytearray(56)
        raw[:8]=BIN_ARRAY_DISC
        raw[8:16]=index.to_bytes(8,"little",signed=True)
        raw[16]=2
        raw[24:56]=bytes(Pubkey.from_string(parent or self.pool))
        return {"owner":owner,"executable":False,
                "data":[base64.b64encode(raw).decode(),"base64"]}

    def test_skips_absent_arrays_without_inventing_keys(self):
        def rpc(rpc,method,params):
            self.assertEqual(method,"getMultipleAccounts")
            return {"context":{"slot":123},"value":[
                self.source(self.active-i) if i in (0,2,4) else None
                for i in range(8)]}
        with patch("arb.meteora_dlmm_bin_preflight.call",side_effect=rpc):
            report=inspect_directional_bin_arrays(
                "http://127.0.0.1:8899",self.pool,self.active,
                input_is_x=True)
        self.assertEqual(report["bin_arrays"],[
            self.index_to_key[self.active-i] for i in (0,2,4)])
        self.assertEqual(report["max_arrays_checked"],8)
        self.assertFalse(report["executable_liquidity_or_quote_verified"])
        self.assertFalse(report["broadcast"])

    def test_rejects_wrong_owner(self):
        with patch("arb.meteora_dlmm_bin_preflight.call",
                   return_value={"context":{"slot":123},"value":[
                       self.source(self.active,owner=str(Pubkey.new_unique())),
                       *([None]*7)]}):
            with self.assertRaisesRegex(ValueError,"owner"):
                inspect_directional_bin_arrays(
                    "http://127.0.0.1:8899",self.pool,self.active,
                    input_is_x=True)

    def test_rejects_changed_pool_identity(self):
        with patch("arb.meteora_dlmm_bin_preflight.call",
                   return_value={"context":{"slot":123},"value":[
                       self.source(self.active,parent=str(Pubkey.new_unique())),
                       *([None]*7)]}):
            with self.assertRaisesRegex(ValueError,"identity"):
                inspect_directional_bin_arrays(
                    "http://127.0.0.1:8899",self.pool,self.active,
                    input_is_x=True)

    def test_rejects_missing_active(self):
        with patch("arb.meteora_dlmm_bin_preflight.call",
                   return_value={"context":{"slot":123},"value":[
                       None,self.source(self.active-1),*([None]*6)]}):
            with self.assertRaisesRegex(ValueError,"active"):
                inspect_directional_bin_arrays(
                    "http://127.0.0.1:8899",self.pool,self.active,
                    input_is_x=True)

    def test_builder_binds_exact_directional_order_and_rejects_reversal(self):
        keys=[str(Pubkey.new_unique()) for _ in range(7)]
        active=self.index_to_key[self.active]
        far=self.index_to_key[self.active-4]
        bins=[active,far]
        evidence={"source_authenticated":True,
                  "pool":self.pool,"active_bin_array_index":self.active,
                  "input_is_x":True,"max_arrays_checked":8,
                  "bin_arrays":bins}
        state={
            "status":0,"token_mint_x_program_flag":0,
            "token_mint_y_program_flag":0,
            "token_x_mint":keys[0],"token_y_mint":keys[1],
            "reserve_x":keys[2],"reserve_y":keys[3],
            "input_mint":keys[0],"output_mint":keys[1],
            "active_bin_array_index":self.active,
            "directional_bin_source":evidence}
        ix=build_swap(self.pool,state,keys[4],keys[5],keys[6],
                      str(Pubkey.new_unique()),bins,100000,1,input_is_x=True)
        self.assertEqual([str(m.pubkey) for m in ix.accounts[-2:]],bins)
        with self.assertRaisesRegex(ValueError,"out of order"):
            build_swap(self.pool,state,keys[4],keys[5],keys[6],
                       str(Pubkey.new_unique()),bins[::-1],100000,1,
                       input_is_x=True)


if __name__=="__main__":
    unittest.main()
