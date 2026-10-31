"""Fifth-venue independent signed audit mutation tests.

These tests generate real Ed25519-signed one-instruction Solana packets.
They are NOT substitute execution proof: the production audit rechecks
real Surfpool transaction/post-SPL evidence, and registry remains blocked.
"""
import base64,hashlib,unittest
from unittest.mock import patch
from solders.keypair import Keypair
from solders.hash import Hash
from solders.transaction import Transaction
from arb.meteora_dlmm import PROGRAM
from arb.meteora_dlmm_swap import build_swap
from arb.meteora_dlmm_bin_preflight import bin_array_pda
from arb.meteora_dlmm_fifth_signed_audit import audit
from arb.meteora_dlmm_signed_registry_merge import merge
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM

SYSTEM="11111111111111111111111111111111"


def fixture():
    pool=str(Keypair().pubkey())
    x=str(Keypair().pubkey())
    y=str(Keypair().pubkey())
    reserve_x=str(Keypair().pubkey())
    reserve_y=str(Keypair().pubkey())
    oracle=str(Keypair().pubkey())
    idx=0
    bin_array=bin_array_pda(pool,idx)
    output=10
    receipts=[]
    native_trials=[]
    for is_x in (True,False):
        for amount in (10000,100000):
            signer=Keypair()
            user=str(signer.pubkey())
            src=str(Keypair().pubkey())
            dst=str(Keypair().pubkey())
            mint_in=x if is_x else y
            mint_out=y if is_x else x
            direction="x_to_y" if is_x else "y_to_x"
            state={"token_x_mint":x,"token_y_mint":y,"reserve_x":reserve_x,
                "reserve_y":reserve_y,"oracle":oracle,"status":0,
                "token_mint_x_program_flag":0,"token_mint_y_program_flag":0,
                "input_mint":mint_in,"output_mint":mint_out,
                "active_bin_array_index":idx}
            instruction=build_swap(pool,state,user,src,dst,oracle,
                [bin_array],amount,output,input_is_x=is_x)
            tx=Transaction.new_signed_with_payer([instruction],
                 signer.pubkey(),[signer],Hash.from_string(SYSTEM))
            signed=bytes(tx)
            native_trials.append({"mint_in":mint_in,"mint_out":mint_out,
                "amount_in":amount,"direction":direction,
                "native_integer_output":output,"official_sdk_output":output})
            receipts.append({"pool":pool,"direction":direction,
                "input_mint":mint_in,"output_mint":mint_out,
                "amount_in":amount,"signed_output":output,
                "official_sdk_output":output,"native_integer_output":output,
                "source_slot":31,"source_sha256":"a"*64,
                "input_token_account":src,"output_token_account":dst,
                "signed_transaction_base64":base64.b64encode(signed).decode(),
                "signed_sha256":hashlib.sha256(signed).hexdigest(),
                "signed_signature":str(tx.signatures[0]),
                "post_spl_account_data_base64":[
                    base64.b64encode(token_account_bytes(mint_in,user,0)).decode(),
                    base64.b64encode(token_account_bytes(mint_out,user,output)).decode()],
                "simulation_logs":["Program "+PROGRAM+" invoke [1]",
                    "Program "+PROGRAM+" success"],
                "status":"SIGNED_DLMM_SDK_NATIVE_SPL_EXACT"})
    source={"venue":"meteora_dlmm","pools":[{
        "address":pool,"mints":[x,y],"source_sha256":"a"*64,
        "source_slot":31}]}
    sdk={"venue":"meteora_dlmm","pools":[{"pool":pool}]}
    signed={"venue":"meteora_dlmm",
        "status":"DLMM_REAL_SIGNED_SDK_NATIVE_SPL_PARITY",
        "signed_parity_verified":True,
        "dlmm_program_elf_sha256":"b"*64,
        "pools":[{"pool":pool,"source_slot":31,"source_sha256":"a"*64,
            "verified":True,"trials":receipts}],
        "actionable":False,"broadcast":False,"live_execution_approved":False,
        "registry_admission_approved":False}
    native={"venue":"meteora_dlmm","verified_pools":1,"pools":[{
        "pool":pool,"source_slot":31,"source_sha256":"a"*64,
        "trials":native_trials}]}
    return source,sdk,signed,native


class DLMMFifthSignedAuditTests(unittest.TestCase):
    def test_signed_packet_and_post_spl_are_independently_audited(self):
        source,sdk,signed,native=fixture()
        with patch("arb.meteora_dlmm_fifth_signed_audit.calculate",
                   return_value=native):
            result=audit(source,sdk,signed)
        self.assertEqual(result["independently_signed_verified_pools"],1)
        self.assertTrue(result["independent_signed_audit_verified"])
        self.assertFalse(result["registry_admission_approved"])

    def test_forged_post_spl_balance_rejected(self):
        source,sdk,signed,native=fixture()
        receipt=signed["pools"][0]["trials"][0]
        receipt["post_spl_account_data_base64"][1]=base64.b64encode(
            token_account_bytes(receipt["output_mint"],
                str(Keypair().pubkey()),10)).decode()
        with patch("arb.meteora_dlmm_fifth_signed_audit.calculate",
                   return_value=native):
            with self.assertRaisesRegex(ValueError,"mint or owner"):
                audit(source,sdk,signed)

    def test_changed_signed_hash_rejected(self):
        source,sdk,signed,native=fixture()
        signed["pools"][0]["trials"][0]["signed_sha256"]="f"*64
        with patch("arb.meteora_dlmm_fifth_signed_audit.calculate",
                   return_value=native):
            with self.assertRaisesRegex(ValueError,"transaction or signature invalid"):
                audit(source,sdk,signed)

    def test_missing_genuine_direction_rejected(self):
        source,sdk,signed,native=fixture()
        signed["pools"][0]["trials"].pop()
        with patch("arb.meteora_dlmm_fifth_signed_audit.calculate",
                   return_value=native):
            with self.assertRaisesRegex(ValueError,"four genuine signed"):
                audit(source,sdk,signed)

    def test_source_mint_change_blocks_durable_registry_admission(self):
        source,sdk,signed,native=fixture()
        registry={"pools":[{"venue":"meteora_dlmm","address":signed["pools"][0]["pool"],
                            "mints":["MISMATCH","TOKENS"]}]}
        with patch("arb.meteora_dlmm_signed_registry_merge.audit",
                   return_value={"independently_signed_verified_pools":1,
                       "pools":[{"pool":signed["pools"][0]["pool"],
                                 "source_sha256":"a"*64,"source_slot":31,
                                 "signed_transaction_hashes":[r["signed_sha256"]
                                      for r in signed["pools"][0]["trials"]]}]}):
            with self.assertRaisesRegex(ValueError,"source mints disagree"):
                merge(registry,source,sdk,signed,required_verified=1)


if __name__=="__main__":
    unittest.main()
