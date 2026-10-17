import base64
import unittest
from unittest.mock import patch
from arb.pumpswap_rejection_audit import audit, inspect
from arb.pumpswap_pool import PROGRAM
from arb.token_vaults import TOKEN_PROGRAM

ADDR = "9DMCBmDYtHbiuL1ctf3M4txTV5ZmdqXipkTgQ1LdFYyv"
MINT = "So11111111111111111111111111111111111111112"
VAULT_A = "1"*32
VAULT_B = "2"*32

def account(owner, data=b"pool"):
    return {"owner":owner,"executable":False,
            "data":[base64.b64encode(data).decode(),"base64"]}

class PumpSwapRejectionAuditTests(unittest.TestCase):
    @patch("arb.pumpswap_rejection_audit.decode")
    @patch("arb.pumpswap_rejection_audit.call")
    def test_synchronized_zero_supply_observation_not_promotion(self, call, decode):
        state={"base_mint":MINT,"base_vault":VAULT_A,"quote_vault":VAULT_B}
        decode.return_value=state
        mint=bytearray(82)
        mint[45]=1
        call.side_effect=[
            {"value":account(PROGRAM)},
            {"context":{"slot":123},"value":[account(PROGRAM),
                account(TOKEN_PROGRAM,bytes(mint)),
                account(TOKEN_PROGRAM),account(TOKEN_PROGRAM)]}]
        result=inspect("rpc",ADDR)
        self.assertEqual(result["mint_observation"],"NATIVE_WSOL_ZERO_SUPPLY")
        self.assertEqual(result["slot"],123)
        self.assertEqual(result["status"],"OBSERVED_NOT_VALIDATED")

    @patch("arb.pumpswap_rejection_audit.decode")
    @patch("arb.pumpswap_rejection_audit.call")
    def test_non_native_zero_supply_remains_distinct(self, call, decode):
        other_mint="3"*32
        decode.return_value={"base_mint":other_mint,
                             "base_vault":VAULT_A,"quote_vault":VAULT_B}
        mint=bytearray(82)
        mint[45]=1
        call.side_effect=[
            {"value":account(PROGRAM)},
            {"context":{"slot":123},"value":[account(PROGRAM),
                account(TOKEN_PROGRAM,bytes(mint)),
                account(TOKEN_PROGRAM),account(TOKEN_PROGRAM)]}]
        result=inspect("rpc",ADDR)
        self.assertEqual(result["mint_observation"],"ZERO_SUPPLY")
        self.assertEqual(result["status"],"OBSERVED_NOT_VALIDATED")

    @patch("arb.pumpswap_rejection_audit.decode")
    @patch("arb.pumpswap_rejection_audit.call")
    def test_nonclassic_mint_is_observed_not_accepted(self, call, decode):
        decode.return_value={"base_mint":MINT,"base_vault":VAULT_A,"quote_vault":VAULT_B}
        call.side_effect=[
            {"value":account(PROGRAM)},
            {"context":{"slot":123},"value":[account(PROGRAM),
                account("OtherTokenProgram"),account(TOKEN_PROGRAM),
                account(TOKEN_PROGRAM)]}]
        result=inspect("rpc",ADDR)
        self.assertEqual(result["mint_observation"],"NON_CLASSIC_TOKEN_PROGRAM")


    @patch("arb.pumpswap_rejection_audit.inspect")
    def test_single_rpc_error_does_not_abort_following_candidates(self, inspect_mock):
        second = "4"*32
        inspect_mock.side_effect=[RuntimeError("RPC unavailable"),
                                  {"address":second,"status":"OBSERVED_NOT_VALIDATED"}]
        result=audit("rpc", {"rejections":[
            {"venue":"pumpswap","address":ADDR},
            {"venue":"pumpswap","address":second}]},limit=2)
        self.assertEqual(result["observed_count"],2)
        self.assertEqual(result["observations"][0]["status"],"RPC_OR_SNAPSHOT_ERROR")
        self.assertEqual(result["observations"][1]["status"],"OBSERVED_NOT_VALIDATED")
        self.assertFalse(result["actionable"])

    @patch("arb.pumpswap_rejection_audit.decode")
    @patch("arb.pumpswap_rejection_audit.call")
    def test_missing_pool_in_snapshot_reports_unsupported(self, call, decode):
        decode.return_value={"base_mint":MINT,"base_vault":VAULT_A,"quote_vault":VAULT_B}
        call.side_effect=[
            {"value":account(PROGRAM)},
            {"context":{"slot":123},"value":[None, account(TOKEN_PROGRAM),
                account(TOKEN_PROGRAM),account(TOKEN_PROGRAM)]}]
        result=inspect("rpc",ADDR)
        self.assertEqual(result["status"],"SNAPSHOT_UNSUPPORTED")

    @patch("arb.pumpswap_rejection_audit.inspect")
    def test_bounded_deduplicated_rejections_never_promoted(self, inspect_mock):
        inspect_mock.return_value={"status":"OBSERVED_NOT_VALIDATED"}
        report={"rejections":[{"venue":"pumpswap","address":ADDR},
                              {"venue":"pumpswap","address":ADDR},
                              {"venue":"orca","address":"3"*32}]}
        result=audit("rpc",report,limit=1)
        self.assertEqual(result["observed_count"],1)
        self.assertEqual(result["observation_categories"],{"OBSERVED_NOT_VALIDATED":1})
        self.assertEqual(result["observations"][0]["original_rejection_reason"],"UNKNOWN")
        self.assertEqual(inspect_mock.call_count,1)
        self.assertFalse(result["actionable"])
        self.assertFalse(result["pool_validation_performed"])
        with self.assertRaises(ValueError):
            audit("rpc",report,limit=21)
