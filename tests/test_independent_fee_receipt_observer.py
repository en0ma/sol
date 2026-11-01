import unittest
from unittest.mock import patch
from arb.independent_fee_receipt_observer import (
    corroborate_signed_fee_receipts,fetch_confirmed_fee_observation,
    inspect_fee_two_read_only_observers)

class FeeReceiptTests(unittest.TestCase):
    def test_reject_missing_or_duplicate_remote_observer(self):
        with self.assertRaises(ValueError):
            corroborate_signed_fee_receipts(b"bogus",[])
        with self.assertRaises(ValueError):
            fetch_confirmed_fee_observation("http://127.0.0.1:8899",b"invalid")

    def test_signed_remote_fee_corroboration_no_payout_claim(self):
        from solders.keypair import Keypair
        from solders.hash import Hash
        from solders.transaction import Transaction
        from solders.system_program import transfer,TransferParams
        from solders.pubkey import Pubkey
        from hashlib import sha256
        import base64
        sender=Keypair()
        instruction=transfer(TransferParams(from_pubkey=sender.pubkey(),
                           to_pubkey=Pubkey.new_unique(),lamports=100))
        tx=Transaction.new_signed_with_payer([instruction],sender.pubkey(),
                                               [sender],Hash.default())
        wire=bytes(tx)
        sig=str(tx.signatures[0])
        digest=sha256(wire).hexdigest()
        base={"signature":sig,"wire_sha256":digest,"slot":123,
              "fee_lamports":5000,"err":None,"confirmed_transaction":True}
        with patch("arb.rpc.call",return_value={"slot":123,
            "transaction":[base64.b64encode(wire).decode(),"base64"],
            "meta":{"fee":5000,"err":None}}):
            a=fetch_confirmed_fee_observation("https://rpc-one.example",wire)
            b=fetch_confirmed_fee_observation("https://rpc-two.example",wire)
        with patch("arb.rpc.call",return_value={"slot":123,
            "transaction":[base64.b64encode(wire).decode(),"base64"],
            "meta":{"fee":5000,"err":None}}):
            direct=inspect_fee_two_read_only_observers(
                "https://rpc-one.example","https://rpc-two.example",wire)
        self.assertEqual(direct["observed_fee_lamports"],5000)
        with self.assertRaises(ValueError):
            inspect_fee_two_read_only_observers(
                "https://rpc-one.example","https://rpc-one.example",wire)
        report=corroborate_signed_fee_receipts(wire,[a,b])
        self.assertEqual(report["observed_fee_lamports"],5000)
        self.assertFalse(report["actual_mainnet_fee_payer_spend_independently_proven"])
        self.assertFalse(report["net_profitability_verified"])
        with self.assertRaises(ValueError):
            corroborate_signed_fee_receipts(wire,[a,{**b,"fee_lamports":6000}])
        with self.assertRaises(ValueError):
            corroborate_signed_fee_receipts(wire,[a,{**b,"rpc_url":a["rpc_url"]}])
        with self.assertRaises(ValueError):
            corroborate_signed_fee_receipts(wire,[a,{**b,"slot":124}])
        with self.assertRaises(ValueError):
            corroborate_signed_fee_receipts(wire,[a,{**b,"wire_sha256":"0"*64}])

if __name__=="__main__":unittest.main()
