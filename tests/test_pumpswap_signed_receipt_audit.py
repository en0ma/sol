import base64
import hashlib
import unittest
from copy import deepcopy
from solders.keypair import Keypair
from solders.hash import Hash
from solders.transaction import Transaction
from arb.pumpswap_pool import PROGRAM
from arb.pumpswap_fee_account import PROGRAM as FEES
from arb.pumpswap_trade_v2 import build_v2,ORDER
from arb.pumpswap_account_resolver import SYSTEM
from arb.pumpswap_signed_receipt_audit import audit
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM


def fixture():
    pool=str(Keypair().pubkey())
    base=str(Keypair().pubkey())
    quote=str(Keypair().pubkey())
    slot=42
    digest="a"*64
    source={"venue":"pumpswap","pools":[{"address":pool,
        "mints":[base,quote],"status":"AUTHENTICATED_SOURCE_ONLY",
        "verified_snapshot_slot":slot,"authenticated_source_sha256":digest,
        "native_quote_candidates":[{"mint_in":mint,"amount_in":amount,
            "native_formula_candidate_out":300,
            "status":"UNVERIFIED_NATIVE_FORMULA_CANDIDATE"}
            for mint in (base,quote) for amount in (10000,100000)]}]}
    quotes=[{"input_mint":mint,"amount_in":amount,
        "official_sdk_output":"300","python_candidate_output":"300",
        "status":"OFFICIAL_SDK_CANDIDATE_EXACT","signed_parity_verified":False}
        for mint in (base,quote) for amount in (10000,100000)]
    sdk={"venue":"pumpswap","signed_parity_verified":False,
        "actionable":False,"registry_admission_approved":False,
        "sdk_candidate_verified_pools":1,"pools":[{
        "address":pool,"source_slot":slot,"source_digest":digest,
        "signed_parity_verified":False,"actionable":False,"trials":quotes}]}
    receipts=[]
    for mint in (base,quote):
        for amount in (10000,100000):
            user=Keypair()
            roles={r:str(Keypair().pubkey()) for r in ORDER}
            roles.update({"pool":pool,"user":str(user.pubkey()),"program":PROGRAM,
                "system_program":SYSTEM,"base_token_program":TOKEN_PROGRAM,
                "quote_token_program":TOKEN_PROGRAM,
                "base_mint":base,"quote_mint":quote,
                "buyback_fee_recipient_authenticated":True})
            direction="sell" if mint==base else "buy_exact_quote_in"
            out_mint=quote if mint==base else base
            ix=build_v2(direction,roles,amount,300)
            tx=Transaction.new_signed_with_payer([ix],user.pubkey(),[user],
                Hash.from_string(SYSTEM))
            serialized=bytes(tx)
            before_input=amount
            after_input=0
            after_output=300
            raw_in=token_account_bytes(mint,str(user.pubkey()),after_input)
            raw_out=token_account_bytes(out_mint,str(user.pubkey()),after_output)
            receipts.append({"pool":pool,"status":"PUMPSWAP_SIGNED_SDK_NATIVE_EXACT",
                "input_mint":mint,"output_mint":out_mint,"amount_in":amount,
                "signed_spl_output":300,"official_sdk_output":300,"native_output":300,
                "source_slot":slot,"source_digest":digest,
                "input_token_account":roles["user_base_token_account"] if mint==base
                    else roles["user_quote_token_account"],
                "output_token_account":roles["user_quote_token_account"] if mint==base
                    else roles["user_base_token_account"],
                "signed_transaction_base64":base64.b64encode(serialized).decode(),
                "signed_sha256":hashlib.sha256(serialized).hexdigest(),
                "signed_signature":str(tx.signatures[0]),
                "initial_input_base_units":before_input,"initial_output_base_units":0,
                "post_spl_account_data_base64":[base64.b64encode(raw_in).decode(),
                    base64.b64encode(raw_out).decode()],
                "simulation_logs":["Program "+PROGRAM+" invoke [1]",
                                   "Program "+PROGRAM+" success"]})
    signed={"venue":"pumpswap","status":"SIGNED_PUMPSWAP_ISOLATED_PARITY",
        "program_elf_sha256":{PROGRAM:"b"*64,FEES:"c"*64},
        "actionable":False,"broadcast":False,"registry_admission_approved":False,
        "signed_proof":{"venue":"pumpswap","status":"PUMPSWAP_SIGNED_SDK_NATIVE_EXACT",
            "signed_parity_verified":True,"actionable":False,"broadcast":False,
            "registry_admission_approved":False,
            "pools":[{"pool":pool,"verified":True,"trials":receipts}]}}
    return source,sdk,signed


class PumpSwapIndependentSignedReceiptAuditTest(unittest.TestCase):
    def test_independent_signed_instruction_and_post_spl_parity(self):
        source,sdk,signed=fixture()
        verdict=audit(source,sdk,signed)
        self.assertEqual(verdict["verified_pools"],1)
        self.assertTrue(verdict["independent_signed_audit_verified"])
        self.assertFalse(verdict["registry_admission_approved"])

    def test_forged_signed_post_spl_balance_fails(self):
        source,sdk,signed=fixture()
        signed["signed_proof"]["pools"][0]["trials"][0]["initial_input_base_units"]=99999
        with self.assertRaisesRegex(ValueError,"SPL debit/output mismatch"):
            audit(source,sdk,signed)

    def test_changed_signed_transaction_hash_fails(self):
        source,sdk,signed=fixture()
        signed["signed_proof"]["pools"][0]["trials"][0]["signed_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"content hash disagreement"):
            audit(source,sdk,signed)

    def test_missing_execution_success_logs_fails(self):
        source,sdk,signed=fixture()
        signed["signed_proof"]["pools"][0]["trials"][0]["simulation_logs"]=[]
        with self.assertRaisesRegex(ValueError,"success logs absent"):
            audit(source,sdk,signed)

    def test_mismatched_source_snapshot_fails(self):
        source,sdk,signed=fixture()
        signed["signed_proof"]["pools"][0]["trials"][0]["source_digest"]="d"*64
        with self.assertRaisesRegex(ValueError,"authenticated snapshot"):
            audit(source,sdk,signed)


if __name__=="__main__":
    unittest.main()
