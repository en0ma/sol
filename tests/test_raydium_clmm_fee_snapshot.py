import unittest
from unittest.mock import patch
from arb.raydium_clmm_fee_snapshot import read,DISC
from arb.raydium_clmm import PROGRAM
import base64


def account(raw,owner=PROGRAM):
    return {"owner":owner,"data":[base64.b64encode(raw).decode(),"base64"]}


class ClmmFeeSnapshotTests(unittest.TestCase):
    @patch("arb.raydium_clmm_fee_snapshot.decode")
    @patch("arb.raydium_clmm_fee_snapshot.call")
    def test_fee_authenticated_in_one_slot(self,call,decode):
        raw=b"pool snapshot"
        config=bytearray(53)
        config[:8]=DISC
        config[47:51]=(3000).to_bytes(4,"little")
        config[51:53]=(64).to_bytes(2,"little")
        decode.return_value={"amm_config":"config","tick_spacing":64}
        call.side_effect=[
            {"value":account(raw)},
            {"context":{"slot":100},"value":[account(raw),account(config)]}]
        report=read("rpc","pool")
        self.assertEqual(report["trade_fee_rate_ppm"],3000)
        self.assertEqual(report["slot"],100)
        self.assertTrue(report["fee_verified_onchain"])
        self.assertFalse(report["swap_simulated"])

    @patch("arb.raydium_clmm_fee_snapshot.decode")
    @patch("arb.raydium_clmm_fee_snapshot.call")
    def test_wrong_config_spacing_rejected(self,call,decode):
        raw=b"pool snapshot"
        config=bytearray(53)
        config[:8]=DISC
        config[47:51]=(3000).to_bytes(4,"little")
        config[51:53]=(32).to_bytes(2,"little")
        decode.return_value={"amm_config":"config","tick_spacing":64}
        call.side_effect=[
            {"value":account(raw)},
            {"context":{"slot":100},"value":[account(raw),account(config)]}]
        with self.assertRaisesRegex(ValueError,"mismatched"):
            read("rpc","pool")

    @patch("arb.raydium_clmm_fee_snapshot.decode")
    @patch("arb.raydium_clmm_fee_snapshot.call")
    def test_mutated_pool_rejected(self,call,decode):
        decode.return_value={"amm_config":"config","tick_spacing":64}
        call.side_effect=[
            {"value":account(b"original")},
            {"context":{"slot":100},"value":[account(b"changed"),account(b"config")]}]
        with self.assertRaisesRegex(ValueError,"changed"):
            read("rpc","pool")
