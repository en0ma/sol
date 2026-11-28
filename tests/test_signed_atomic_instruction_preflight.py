import unittest
from arb.signed_atomic_instruction_preflight import inspect_signed_legacy_order

try:
    from solders.keypair import Keypair
    from solders.hash import Hash
    from solders.transaction import Transaction
    from solders.instruction import Instruction,AccountMeta
    from solders.pubkey import Pubkey
    HAVE_SOLDERS=True
except ImportError:
    HAVE_SOLDERS=False

@unittest.skipUnless(HAVE_SOLDERS,"solders required for signed transaction serialization")
class SignedAtomicInstructionPreflightTests(unittest.TestCase):
    def setUp(self):
        self.payer=Keypair()
        self.first=str(Keypair().pubkey())
        self.second=str(Keypair().pubkey())
        self.middle=str(Keypair().pubkey())
        self.other=str(Keypair().pubkey())

    def wire(self,*,reverse=False,second_uses_middle=True,duplicate=False):
        meta=lambda account:AccountMeta(Pubkey.from_string(account),False,True)
        first=Instruction(Pubkey.from_string(self.first),b"first",
                          [meta(self.middle)])
        second=Instruction(Pubkey.from_string(self.second),b"second",
                           [meta(self.middle if second_uses_middle else self.other)])
        instructions=[second,first] if reverse else [first,second]
        if duplicate:
            instructions.append(first)
        tx=Transaction.new_signed_with_payer(
            instructions,self.payer.pubkey(),[self.payer],Hash.default())
        return bytes(tx)

    def test_signed_transaction_instruction_order_and_intermediate_reference(self):
        result=inspect_signed_legacy_order(
            self.wire(),self.first,self.second,
            intermediate_account=self.middle)
        self.assertTrue(result["instruction_order_verified"])
        self.assertTrue(result["shared_intermediate_account_referenced"])
        self.assertEqual(result["first_instruction_index"],0)
        self.assertEqual(result["second_instruction_index"],1)
        self.assertFalse(result["intermediate_intra_transaction_consumption_verified"])
        self.assertFalse(result["rollback_failure_case_verified"])
        self.assertFalse(result["signed_atomic_simulation_verified"])
        self.assertFalse(result["broadcast"])

    def test_reversed_order_rejected(self):
        with self.assertRaisesRegex(ValueError,"reversed"):
            inspect_signed_legacy_order(self.wire(reverse=True),
                                        self.first,self.second,
                                        intermediate_account=self.middle)

    def test_missing_intermediate_on_second_leg_rejected(self):
        with self.assertRaisesRegex(ValueError,"both venue instructions"):
            inspect_signed_legacy_order(self.wire(second_uses_middle=False),
                                        self.first,self.second,
                                        intermediate_account=self.middle)

    def test_duplicate_first_program_rejected(self):
        with self.assertRaisesRegex(ValueError,"exactly one"):
            inspect_signed_legacy_order(self.wire(duplicate=True),
                                        self.first,self.second,
                                        intermediate_account=self.middle)

    def test_wrong_claimed_program_rejected(self):
        with self.assertRaisesRegex(ValueError,"exactly one"):
            inspect_signed_legacy_order(self.wire(),str(Keypair().pubkey()),self.second,
                                        intermediate_account=self.middle)

    def test_tampered_signed_transaction_rejected(self):
        wire=bytearray(self.wire())
        # Signature bytes follow the leading short-vector signature count.
        wire[1]^=1
        with self.assertRaisesRegex(ValueError,"malformed or unsupported"):
            inspect_signed_legacy_order(bytes(wire),self.first,self.second,
                                        intermediate_account=self.middle)

    def test_invalid_transaction_bytes_rejected(self):
        with self.assertRaises(ValueError):
            inspect_signed_legacy_order(b"not-a-transaction",self.first,self.second)
