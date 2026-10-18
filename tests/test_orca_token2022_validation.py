import base64
import unittest
from unittest.mock import patch

from arb.orca_token2022_validation import snapshot, extension_risk, observe_oracle_account
from arb.orca_whirlpool import PROGRAM, b58
from arb.token2022_extensions import TOKEN_2022
from arb.token_vaults import TOKEN_PROGRAM

POOL="1"*32
VA=b58(bytes([3])*32)
VB=b58(bytes([4])*32)
MA=b58(bytes([1])*32)
MB=b58(bytes([2])*32)
STATE={"token_vault_a":VA,"token_vault_b":VB,
       "token_mint_a":MA,"token_mint_b":MB,"liquidity":100}

def acct(owner,raw):
    return {"owner":owner,"executable":False,
            "data":[base64.b64encode(raw).decode(),"base64"]}

def mint():
    raw=bytearray(82)
    raw[45]=1
    raw[36:44]=(100000).to_bytes(8,"little")
    return bytes(raw)

def vault(mint_byte,program):
    raw=bytearray(166 if program==TOKEN_2022 else 165)
    raw[:32]=bytes([mint_byte])*32
    raw[32:64]=bytes([7])*32
    raw[64:72]=(100).to_bytes(8,"little")
    raw[108]=1
    if program==TOKEN_2022:raw[165]=2
    return bytes(raw)

class OrcaToken2022StructuralTests(unittest.TestCase):
    @patch("arb.orca_token2022_validation.decode",return_value=STATE)
    @patch("arb.orca_token2022_validation.fetch_pool",return_value=STATE)
    @patch("arb.orca_token2022_validation.call")
    def test_mixed_program_accounts_structural_only(self,call,fetch,decode):
        call.return_value={"context":{"slot":55},"value":[
            acct(PROGRAM,b"pool"),
            acct(TOKEN_PROGRAM,vault(1,TOKEN_PROGRAM)),
            acct(TOKEN_2022,vault(2,TOKEN_2022)),
            acct(TOKEN_PROGRAM,mint()),
            acct(TOKEN_2022,mint())]}
        output=snapshot("rpc",POOL)
        self.assertTrue(output["structurally_verified"])
        self.assertEqual(output["slot"],55)
        self.assertEqual(output["pool"],{"address":POOL,**STATE})
        self.assertEqual(output["mints"],[MA,MB])
        self.assertFalse(output["actionable"])
        self.assertFalse(output["executable_quote"])
        self.assertFalse(output["effective_fee_verified"])
        self.assertEqual(call.call_args.args[1],"getMultipleAccounts")
        self.assertEqual(len(call.call_args.args[2][0]),5)
        self.assertNotIn("minContextSlot",call.call_args.args[2][1])

    @patch("arb.orca_token2022_validation.decode",return_value=STATE)
    @patch("arb.orca_token2022_validation.fetch_pool",return_value=STATE)
    @patch("arb.orca_token2022_validation.call")
    def test_wrong_program_vault_cannot_pass(self,call,fetch,decode):
        call.return_value={"context":{"slot":55},"value":[
            acct(PROGRAM,b"pool"),acct("wrong",vault(1,TOKEN_PROGRAM)),
            acct(TOKEN_2022,vault(2,TOKEN_2022)),
            acct(TOKEN_PROGRAM,mint()),acct(TOKEN_2022,mint())]}
        with self.assertRaises(ValueError):
            snapshot("rpc",POOL)

    @patch("arb.orca_token2022_validation.fetch_pool",return_value=STATE)
    @patch("arb.orca_token2022_validation.call")
    def test_missing_slot_fails_closed(self,call,fetch):
        call.return_value={"value":[]}
        with self.assertRaises(ValueError):
            snapshot("rpc",POOL)

class Token2022ExtensionRiskTests(unittest.TestCase):
    def test_transfer_fee_and_hook_require_specialized_quote(self):
        risk=extension_risk([
            {"extension_types":[3,18,19,1,14]},
            {"extension_types":[]}])
        self.assertEqual(risk["blocking_extension_ids"],[1,14])
        self.assertTrue(risk["requires_specialized_quote_support"])
        self.assertFalse(risk["fee_mode_verified"])
        self.assertFalse(risk["executable_quote"])

    def test_unknown_extension_fails_closed_for_quoting(self):
        risk=extension_risk([
            {"extension_types":[65535]},{"extension_types":[]}])
        self.assertEqual(risk["blocking_extension_ids"],[65535])
        self.assertFalse(risk["executable_quote"])

    def test_metadata_only_still_needs_quote_authentication(self):
        risk=extension_risk([
            {"extension_types":[3,18,19]},{"extension_types":[]}])
        self.assertEqual(risk["blocking_extension_ids"],[])
        self.assertFalse(risk["fee_mode_verified"])
        self.assertFalse(risk["executable_quote"])

    @patch("arb.orca_token2022_validation.decode",return_value=STATE)
    @patch("arb.orca_token2022_validation.fetch_pool",return_value=STATE)
    @patch("arb.orca_token2022_validation.call")
    def test_rpc_stale_context_fails_closed(self,call,fetch,decode):
        call.return_value={"context":{"slot":55},"value":[
            acct(PROGRAM,b"pool"),
            acct(TOKEN_PROGRAM,vault(1,TOKEN_PROGRAM)),
            acct(TOKEN_2022,vault(2,TOKEN_2022)),
            acct(TOKEN_PROGRAM,mint()),acct(TOKEN_2022,mint())]}
        with self.assertRaisesRegex(ValueError,"stale"):
            snapshot("rpc",POOL,min_context_slot=56)
        self.assertEqual(call.call_args.args[2][1]["minContextSlot"],56)

class OracleAccountObservationTests(unittest.TestCase):
    @patch("arb.orca_token2022_validation.call")
    def test_owner_checked_but_not_same_slot_verified(self,rpc):
        rpc.return_value={"context":{"slot":60},"value":acct(PROGRAM,b"12345678")}
        evidence=observe_oracle_account("rpc",POOL,55)
        self.assertTrue(evidence["oracle_account_present"])
        self.assertTrue(evidence["oracle_owner_checked"])
        self.assertFalse(evidence["same_slot_verified"])
        self.assertFalse(evidence["executable_quote"])
        self.assertEqual(rpc.call_args.args[1],"getAccountInfo")
        self.assertEqual(rpc.call_args.args[2][1]["minContextSlot"],55)

    @patch("arb.orca_token2022_validation.call")
    def test_wrong_oracle_owner_fails(self,rpc):
        rpc.return_value={"context":{"slot":60},"value":acct(TOKEN_PROGRAM,b"12345678")}
        with self.assertRaises(ValueError):
            observe_oracle_account("rpc",POOL,55)

    @patch("arb.orca_token2022_validation.call")
    def test_missing_oracle_is_not_verified(self,rpc):
        rpc.return_value={"context":{"slot":60},"value":None}
        evidence=observe_oracle_account("rpc",POOL,55)
        self.assertFalse(evidence["oracle_account_present"])
        self.assertFalse(evidence["oracle_owner_checked"])
        self.assertFalse(evidence["actionable"])
