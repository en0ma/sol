import base64
import hashlib
import unittest
from solders.hash import Hash
from solders.keypair import Keypair
from solders.system_program import transfer,TransferParams
from solders.transaction import Transaction,VersionedTransaction
from solders.message import MessageV0
from arb.m5_independent_signed_wire_verifier import verify_signed_pair
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

class IndependentSignedWireVerifierTests(unittest.TestCase):
    def receipt(self,versioned=False):
        payer=Keypair()
        recipient=Keypair().pubkey()
        blockhash=Hash.default()
        tx=[]
        for lamports in (2,3):
            first=transfer(TransferParams(from_pubkey=payer.pubkey(),
                to_pubkey=recipient,lamports=1))
            ix=transfer(TransferParams(from_pubkey=payer.pubkey(),
                to_pubkey=recipient,lamports=lamports))
            if versioned:
                msg=MessageV0.try_compile(payer.pubkey(),[first,ix],[],blockhash)
                signed=VersionedTransaction(msg,[payer])
            else:
                signed=Transaction.new_signed_with_payer(
                    [first,ix],payer.pubkey(),[payer],blockhash)
            tx.append(signed)
        pos,neg=tx
        pos_raw,neg_raw=bytes(pos),bytes(neg)
        return {"signed_transaction_wire_base64":
                    base64.b64encode(pos_raw).decode("ascii"),
                "negative_signed_transaction_wire_base64":
                    base64.b64encode(neg_raw).decode("ascii"),
                "signed_transaction_sha256":hashlib.sha256(pos_raw).hexdigest(),
                "negative_signed_transaction_sha256":hashlib.sha256(neg_raw).hexdigest(),
                "signed_transaction_signature":str(pos.signatures[0]),
                "negative_signed_transaction_signature":str(neg.signatures[0]),
                "signed_packet_bytes":len(pos_raw),
                "negative_packet_bytes":len(neg_raw),
                "legs":2,**SAFE}
    def test_real_legacy_signatures_and_hashes(self):
        result=verify_signed_pair(self.receipt())
        self.assertTrue(result["positive_signed_message_verified"])
        self.assertTrue(result["negative_signed_message_verified"])
        self.assertTrue(result["signed_prefix_instructions_identical_verified"])
        self.assertTrue(result["signed_final_instruction_changed_verified"])
        self.assertFalse(result["broadcast"])
    def test_real_versioned_signatures_and_hashes(self):
        result=verify_signed_pair(self.receipt(versioned=True))
        self.assertTrue(result["same_signer_and_blockhash_verified"])
    def test_mutated_wire_with_recomputed_digest_cannot_pass_signature(self):
        receipt=self.receipt()
        raw=bytearray(base64.b64decode(receipt["signed_transaction_wire_base64"]))
        raw[-1]^=1
        receipt["signed_transaction_wire_base64"]=base64.b64encode(raw).decode()
        receipt["signed_transaction_sha256"]=hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ValueError,"signature"):
            verify_signed_pair(receipt)
    def test_reported_signature_without_matching_wire_rejected(self):
        receipt=self.receipt()
        receipt["signed_transaction_signature"]="incorrect"
        with self.assertRaisesRegex(ValueError,"signature"):
            verify_signed_pair(receipt)
    def test_reported_sha_without_matching_wire_rejected(self):
        receipt=self.receipt()
        receipt["negative_signed_transaction_sha256"]="a"*64
        with self.assertRaisesRegex(ValueError,"digest"):
            verify_signed_pair(receipt)
    def test_missing_full_signed_wire_not_a_receipt(self):
        receipt=self.receipt()
        receipt.pop("signed_transaction_wire_base64")
        with self.assertRaisesRegex(ValueError,"missing"):
            verify_signed_pair(receipt)
    def test_unsafe_flag_cannot_upgrade_signed_acceptance(self):
        receipt=self.receipt()
        receipt["broadcast"]=True
        with self.assertRaisesRegex(ValueError,"nonbroadcast"):
            verify_signed_pair(receipt)
if __name__=="__main__":unittest.main()

class SignedFeeMessageBindingTests(IndependentSignedWireVerifierTests):
    def test_matching_fee_message_digest_is_independently_accepted(self):
        from solders.message import to_bytes_versioned
        receipt=self.receipt(versioned=True)
        raw=base64.b64decode(receipt["signed_transaction_wire_base64"])
        tx=VersionedTransaction.from_bytes(raw)
        receipt["signed_message_fee_estimate"]={
            "status":"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY",
            "signed_message_sha256":hashlib.sha256(
                to_bytes_versioned(tx.message)).hexdigest(),
            "estimated_fee_lamports":5000,"paid_fee_verified":False,
            "fee_payer_asset":"SOL",**SAFE}
        verdict=verify_signed_pair(receipt)
        self.assertTrue(verdict["signed_message_fee_digest_bound"])

    def test_forged_signed_fee_quote_cannot_price_receipt(self):
        receipt=self.receipt()
        receipt["signed_message_fee_estimate"]={
            "status":"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY",
            "signed_message_sha256":"f"*64,"estimated_fee_lamports":5000,
            "paid_fee_verified":False,"fee_payer_asset":"SOL",**SAFE}
        with self.assertRaisesRegex(ValueError,"fee estimate"):
            verify_signed_pair(receipt)

    def test_negative_fee_and_unsafe_fee_provenance_rejected(self):
        for field,value in (("estimated_fee_lamports",-1),("broadcast",True),
                            ("paid_fee_verified",True)):
            with self.subTest(field=field):
                receipt=self.receipt()
                receipt["signed_message_fee_estimate"]={
                    "status":"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY",
                    "signed_message_sha256":"f"*64,
                    "estimated_fee_lamports":5000,
                    "paid_fee_verified":False,
                    "fee_payer_asset":"SOL",**SAFE}
                receipt["signed_message_fee_estimate"][field]=value
                with self.assertRaises(ValueError):
                    verify_signed_pair(receipt)
