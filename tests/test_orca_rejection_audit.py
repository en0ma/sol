import unittest
from unittest.mock import patch

from arb.orca_rejection_audit import audit, classify, observe_vault, TOKEN_2022
from arb.orca_whirlpool import PROGRAM

ADDRESS="7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm"

class OrcaRejectionAuditTests(unittest.TestCase):
    @patch("arb.orca_rejection_audit.call")
    def test_missing_pool_is_not_promoted(self, rpc):
        rpc.return_value={"value":None}
        r=classify("rpc",ADDRESS)
        self.assertEqual(r["category"],"POOL_MISSING")
        self.assertFalse(r["verified"])
        self.assertFalse(r["actionable"])

    @patch("arb.orca_rejection_audit.call")
    def test_wrong_program_is_reported_not_accepted(self, rpc):
        rpc.return_value={"value":{"owner":"wrong-program","executable":False}}
        r=classify("rpc",ADDRESS)
        self.assertEqual(r["category"],"POOL_OWNER_MISMATCH")
        self.assertEqual(r["pool_owner"],"wrong-program")
        self.assertFalse(r["verified"])

    @patch("arb.orca_rejection_audit.classify")
    def test_audit_reads_only_rejected_orca_addresses(self, classify):
        classify.return_value={"category":"POOL_MISSING","verified":False}
        report=audit("rpc",{"rejections":[{"venue":"orca","address":ADDRESS},
           {"venue":"pumpswap","address":"other"}]},limit=1)
        self.assertEqual(report["audited"],1)
        self.assertEqual(report["total_rejections"],2)
        self.assertEqual(report["verified_count"],0)
        self.assertFalse(report["mainnet_broadcast"])
        classify.assert_called_once_with("rpc",ADDRESS)

    def test_bounded_audit(self):
        with self.assertRaises(ValueError):
            audit("rpc",{"rejections":[]},limit=201)

class Token2022ObservationTests(unittest.TestCase):
    def test_token2022_vault_observation_never_claims_execution(self):
        import base64
        from arb.orca_whirlpool import b58
        raw=bytearray(170)
        raw[:32]=bytes([3])*32
        raw[32:64]=bytes([7])*32
        raw[64:72]=(101).to_bytes(8,"little")
        raw[108]=1
        raw[165]=2
        account={"owner":TOKEN_2022,"executable":False,
                 "data":[base64.b64encode(raw).decode(),"base64"]}
        obs=observe_vault(account,b58(bytes([3])*32))
        self.assertTrue(obs["mint_matches_pool"])
        self.assertEqual(obs["amount_base_units"],101)
        self.assertEqual(obs["token_program"],"token_2022")
        self.assertEqual(obs["extension_state"],"INVENTORIED_NOT_EXECUTION_AUTHENTICATED")
        self.assertFalse(obs["eligible_for_executable_quote"])

    def test_truncated_extension_account_is_rejected(self):
        import base64
        account={"owner":TOKEN_2022,"executable":False,
                 "data":[base64.b64encode(bytes(40)).decode(),"base64"]}
        with self.assertRaises(ValueError):
            observe_vault(account,"mint")

    def test_valid_extension_is_inventoried_without_execution(self):
        import base64
        from arb.orca_whirlpool import b58
        raw=bytearray(166+4+8)
        raw[:32]=bytes([3])*32
        raw[32:64]=bytes([7])*32
        raw[64:72]=(101).to_bytes(8,"little")
        raw[108]=1
        raw[165]=2
        raw[166:168]=(2).to_bytes(2,"little")
        raw[168:170]=(8).to_bytes(2,"little")
        account={"owner":TOKEN_2022,"executable":False,
                 "data":[base64.b64encode(raw).decode(),"base64"]}
        obs=observe_vault(account,b58(bytes([3])*32))
        self.assertEqual(obs["extension_types"],[2])
        self.assertFalse(obs["eligible_for_executable_quote"])

    def test_duplicate_extension_fails_closed(self):
        from arb.token2022_extensions import extension_types
        raw=bytearray(174)
        raw[165]=2
        raw[166:168]=(2).to_bytes(2,"little")
        raw[170:172]=(2).to_bytes(2,"little")
        with self.assertRaises(ValueError):
            extension_types(bytes(raw),2)
