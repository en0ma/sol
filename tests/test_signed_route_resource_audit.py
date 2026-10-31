"""Signed offline packet/resource diagnostics must never certify network fees."""
import hashlib
import unittest
import base64
from unittest.mock import patch
from solders.hash import Hash
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction
from solders.transaction import Transaction
from arb.signed_route_resource_audit import inspect_signed_offline_resources, quote_signed_message_fee_offline, inspect_local_recorded_transaction_fee, reconcile_local_fee_observations


def signed_wire():
    signer=Keypair()
    ix=Instruction(Pubkey.new_unique(),bytes([1]),[])
    tx=Transaction.new_signed_with_payer([ix],signer.pubkey(),[signer],Hash.default())
    tx.verify()
    wire=bytes(tx)
    return wire,hashlib.sha256(wire).hexdigest()


class SignedResourceAuditTests(unittest.TestCase):
    def test_valid_signed_wire_is_not_fee_acceptance(self):
        wire,digest=signed_wire()
        out=inspect_signed_offline_resources(
            wire,{"err":None,"unitsConsumed":100_000},expected_wire_sha256=digest)
        self.assertEqual(out["signed_packet_sha256"],digest)
        self.assertEqual(out["observed_simulation_compute_units"],100_000)
        self.assertEqual(out["signatures_count"],1)
        self.assertIsNone(out["fee_lamports"])
        for field in ("independent_fee_paid_verified","actionable",
                      "live_execution_approved","broadcast",
                      "signed_cpi_per_leg_verified","rollback_control_verified"):
            self.assertFalse(out[field])
    def test_tamper_digest_and_invalid_signature(self):
        wire,digest=signed_wire()
        with self.assertRaisesRegex(ValueError,"digest mismatch"):
            inspect_signed_offline_resources(wire,{"err":None,"unitsConsumed":100},expected_wire_sha256="0"*64)
        altered=bytearray(wire)
        altered[10]^=1
        altered=bytes(altered)
        with self.assertRaisesRegex(ValueError,"Ed25519"):
            inspect_signed_offline_resources(
                altered,{"err":None,"unitsConsumed":100},
                expected_wire_sha256=hashlib.sha256(altered).hexdigest())
    def test_bad_compute_and_simulated_failure_blocked(self):
        wire,digest=signed_wire()
        for result in ({"unitsConsumed":0},{"unitsConsumed":True},
                       {"unitsConsumed":1_400_001},{"unitsConsumed":1.5},
                       {"err":{"InstructionError":[0,"Custom"]},"unitsConsumed":100},
                       {}):
            with self.subTest(result=result):
                with self.assertRaises(ValueError):
                    inspect_signed_offline_resources(wire,result,expected_wire_sha256=digest)
    @patch("arb.rpc.call")
    def test_fee_quote_is_bound_to_signed_message_but_never_paid(self, call):
        wire,digest=signed_wire()
        call.return_value={"context":{"slot":123},"value":5000}
        report=quote_signed_message_fee_offline(
            "http://127.0.0.1:8899",wire,{"err":None,"unitsConsumed":30000},
            expected_wire_sha256=digest)
        self.assertEqual(report["quoted_fee_lamports"],5000)
        self.assertEqual(report["quote_context_slot"],123)
        self.assertIsNone(report["fee_lamports"])
        self.assertFalse(report["independent_fee_paid_verified"])
        self.assertFalse(report["actionable"])
        args=call.call_args.args
        self.assertEqual(args[1],"getFeeForMessage")
        self.assertEqual(base64.b64decode(args[2][0]),bytes(
            __import__("solders.transaction",fromlist=["VersionedTransaction"]).VersionedTransaction.from_bytes(wire).message))
        self.assertEqual(args[2][1],{"commitment":"processed"})

    @patch("arb.rpc.call")
    def test_fee_quote_invalid_or_absent_never_accepted(self, call):
        wire,digest=signed_wire()
        for response in ({"context":{"slot":12},"value":None},
                         {"context":{"slot":12},"value":True},
                         {"context":{"slot":12},"value":-1},
                         {"context":{"slot":12},"value":2**64},
                         {"context":{"slot":True},"value":123},
                         {"value":123},None):
            with self.subTest(response=response):
                call.return_value=response
                with self.assertRaises(ValueError):
                    quote_signed_message_fee_offline(
                        "http://127.0.0.1:8899",wire,{"unitsConsumed":1},
                        expected_wire_sha256=digest)
        with self.assertRaises(ValueError):
            quote_signed_message_fee_offline(
                "https://api.mainnet-beta.solana.com",wire,{"unitsConsumed":1},
                expected_wire_sha256=digest)


    @patch("arb.rpc.call")
    def test_local_recorded_receipt_exact_wire_fee_diagnostic_only(self, call):
        wire,digest=signed_wire()
        call.return_value={
            "slot":55,"transaction":[base64.b64encode(wire).decode(),"base64"],
            "meta":{"err":None,"fee":5100,"computeUnitsConsumed":8000}}
        out=inspect_local_recorded_transaction_fee(
            "http://127.0.0.1:8899",wire,
            {"err":None,"unitsConsumed":8000},expected_wire_sha256=digest)
        self.assertEqual(out["local_recorded_fee_lamports"],5100)
        self.assertEqual(out["local_recorded_slot"],55)
        self.assertIsNone(out["fee_lamports"])
        self.assertFalse(out["independent_fee_paid_verified"])
        self.assertFalse(out["broadcast"])
        self.assertEqual(call.call_args.args[1],"getTransaction")
        self.assertEqual(call.call_args.args[2][0],out["first_signature"])

    @patch("arb.rpc.call")
    def test_local_recorded_receipt_rejects_forgery_and_missing_fields(self, call):
        wire,digest=signed_wire()
        correct={"slot":55,"transaction":[base64.b64encode(wire).decode(),"base64"],
                 "meta":{"err":None,"fee":5000,"computeUnitsConsumed":8000}}
        other,_=signed_wire()
        for altered in (
            None,
            {**correct,"transaction":[base64.b64encode(other).decode(),"base64"]},
            {**correct,"transaction":["not base64!","base64"]},
            {**correct,"slot":True},
            {**correct,"meta":{**correct["meta"],"fee":True}},
            {**correct,"meta":{**correct["meta"],"computeUnitsConsumed":0}},
            {**correct,"meta":{**correct["meta"],"err":{"InstructionError":[0,"Custom"]}}},
            {**correct,"transaction":[base64.b64encode(wire).decode(),"base58"]},
        ):
            with self.subTest(altered=altered):
                call.return_value=altered
                with self.assertRaises(ValueError):
                    inspect_local_recorded_transaction_fee(
                        "http://127.0.0.1:8899",wire,
                        {"err":None,"unitsConsumed":8000},
                        expected_wire_sha256=digest)
        with self.assertRaises(ValueError):
            inspect_local_recorded_transaction_fee(
                "https://api.mainnet-beta.solana.com",wire,
                {"err":None,"unitsConsumed":8000},expected_wire_sha256=digest)


    @patch("arb.rpc.call")
    def test_correlate_local_quote_and_recording_without_proving_fee(self, call):
        wire,digest=signed_wire()
        simulation={"err":None,"unitsConsumed":8000}
        call.return_value={"context":{"slot":19},"value":5000}
        quote=quote_signed_message_fee_offline(
            "http://127.0.0.1:8899",wire,simulation,expected_wire_sha256=digest)
        call.return_value={"slot":20,
            "transaction":[base64.b64encode(wire).decode(),"base64"],
            "meta":{"err":None,"fee":5100,"computeUnitsConsumed":8100}}
        recorded=inspect_local_recorded_transaction_fee(
            "http://127.0.0.1:8899",wire,simulation,expected_wire_sha256=digest)
        source="a"*64
        out=reconcile_local_fee_observations(
            quote,recorded,source_snapshot_sha256=source)
        self.assertEqual(out["quote_recorded_fee_difference_lamports"],100)
        self.assertEqual(out["source_snapshot_sha256_unverified"],source)
        self.assertFalse(out["source_snapshot_authenticated"])
        self.assertFalse(out["net_profitability_verified"])
        self.assertIsNone(out["fee_lamports"])
        self.assertFalse(out["broadcast"])
        for altered_q,altered_r,source_hash in (
            ({**quote,"first_signature":"wrong"},recorded,source),
            ({**quote,"observed_simulation_compute_units":7},recorded,source),
            (quote,{**recorded,"signed_packet_sha256":"b"*64},source),
            (quote,{**recorded,"local_recorded_fee_lamports":True},source),
            (quote,{**recorded,"local_recorded_fee_lamports":-1},source),
            ({**quote,"independent_fee_paid_verified":True},recorded,source),
            ({**quote,"fee_lamports":5000},recorded,source),
            ({**quote,"actionable":True},recorded,source),
            (quote,recorded,"not-a-sha"),
        ):
            with self.subTest(quote=altered_q,recorded=altered_r,source=source_hash):
                with self.assertRaises(ValueError):
                    reconcile_local_fee_observations(
                        altered_q,altered_r,source_snapshot_sha256=source_hash)

    @patch("arb.rpc.call")
    def test_snapshot_bytes_must_match_declared_digest(self, call):
        wire,digest=signed_wire()
        simulation={"err":None,"unitsConsumed":8000}
        call.return_value={"context":{"slot":19},"value":5000}
        quote=quote_signed_message_fee_offline(
            "http://127.0.0.1:8899",wire,simulation,expected_wire_sha256=digest)
        call.return_value={"slot":20,
            "transaction":[base64.b64encode(wire).decode(),"base64"],
            "meta":{"err":None,"fee":5100,"computeUnitsConsumed":8100}}
        recorded=inspect_local_recorded_transaction_fee(
            "http://127.0.0.1:8899",wire,simulation,expected_wire_sha256=digest)
        raw=b"source-pool-state-original-bytes"
        source=hashlib.sha256(raw).hexdigest()
        checked=reconcile_local_fee_observations(
            quote,recorded,source_snapshot_sha256=source,source_snapshot_bytes=raw)
        self.assertTrue(checked["source_snapshot_content_hash_checked"])
        self.assertFalse(checked["source_snapshot_authenticated"])
        self.assertFalse(checked["net_profitability_verified"])
        self.assertFalse(checked["broadcast"])
        for forged in (b"other bytes",b"",raw+b"tampered"):
            with self.subTest(forged=forged):
                with self.assertRaisesRegex(ValueError,"content hash mismatch"):
                    reconcile_local_fee_observations(
                        quote,recorded,source_snapshot_sha256=source,
                        source_snapshot_bytes=forged)
        for malformed in (True,"text",bytearray(raw),b"x"*(4_194_304+1)):
            with self.assertRaisesRegex(ValueError,"content hash mismatch"):
                reconcile_local_fee_observations(
                    quote,recorded,source_snapshot_sha256=source,
                    source_snapshot_bytes=malformed)
        unbound=reconcile_local_fee_observations(
            quote,recorded,source_snapshot_sha256=source)
        self.assertFalse(unbound["source_snapshot_content_hash_checked"])

    def test_wire_size_and_digest_type_blocked(self):
        wire,digest=signed_wire()
        for data,sha in ((wire+b"x"*1232,digest),(wire,"f"*63),
                         (wire,None),(wire.hex(),digest)):
            with self.assertRaises(ValueError):
                inspect_signed_offline_resources(data,{"unitsConsumed":1},expected_wire_sha256=sha)


if __name__=="__main__":
    unittest.main()
