import base64
import unittest
from unittest.mock import patch
from solders.hash import Hash
from solders.keypair import Keypair
from solders.message import Message,MessageV0,to_bytes_versioned
from solders.transaction import Transaction,VersionedTransaction
from arb.m5_signed_message_fee_estimate import estimate_signed_message_fee
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
class SignedVersionedFeeEstimateTests(unittest.TestCase):
    def message_and_transaction(self,versioned):
        signer=Keypair()
        if versioned:
            message=MessageV0.try_compile(signer.pubkey(),[],[],Hash.default())
            return message,VersionedTransaction(message,[signer])
        message=Message.new_with_blockhash([],signer.pubkey(),Hash.default())
        return message,Transaction.new_signed_with_payer(
            [],signer.pubkey(),[signer],Hash.default())
    @patch("arb.m5_signed_message_fee_estimate.local_rpc_only")
    @patch("arb.m5_signed_message_fee_estimate.call")
    def test_versioned_message_must_preserve_wire_version_prefix(self,call,local):
        message,tx=self.message_and_transaction(True)
        call.return_value={"value":5000}
        result=estimate_signed_message_fee("http://127.0.0.1:8899",tx)
        self.assertEqual(result["estimated_fee_lamports"],5000)
        self.assertFalse(result["paid_fee_verified"])
        args=call.call_args.args
        encoded=base64.b64decode(args[2][0])
        self.assertEqual(encoded,to_bytes_versioned(message))
        self.assertEqual(encoded[0] & 0x80,0x80)
        self.assertFalse(result["broadcast"])
    @patch("arb.m5_signed_message_fee_estimate.local_rpc_only")
    @patch("arb.m5_signed_message_fee_estimate.call")
    def test_legacy_message_uses_canonical_signed_encoding(self,call,local):
        message,tx=self.message_and_transaction(False)
        call.return_value={"value":5000}
        result=estimate_signed_message_fee("http://127.0.0.1:8899",tx)
        self.assertEqual(result["status"],"SIGNED_MESSAGE_FEE_ESTIMATE_ONLY")
        args=call.call_args.args
        self.assertEqual(base64.b64decode(args[2][0]),to_bytes_versioned(message))
    @patch("arb.m5_signed_message_fee_estimate.local_rpc_only")
    @patch("arb.m5_signed_message_fee_estimate.call")
    def test_unsupported_rpc_fee_never_becomes_zero(self,call,local):
        _,tx=self.message_and_transaction(True)
        call.side_effect=ValueError("Invalid message: IndexOutOfBounds")
        result=estimate_signed_message_fee("http://127.0.0.1:8899",tx)
        self.assertEqual(result["status"],"FEE_ESTIMATE_UNAVAILABLE")
        self.assertNotIn("estimated_fee_lamports",result)
        self.assertFalse(result["broadcast"])
if __name__=="__main__":unittest.main()
