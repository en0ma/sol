"""Legacy packet and per-leg comparison evidence checks, synthetic only."""
import base64
import unittest
from unittest.mock import patch
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.hash import Hash
from solders.instruction import Instruction
from solders.transaction import Transaction
from arb import blockzilla_pair_evidence as e


class PairEvidenceTests(unittest.TestCase):
    def test_packet_round_trip_and_bad_signature_rejected(self):
        payer = Keypair()
        tx = Transaction.new_signed_with_payer(
            [Instruction(Pubkey.new_unique(), b"a", []),
             Instruction(Pubkey.new_unique(), b"b", [])],
            payer.pubkey(), [payer], Hash.new_unique())
        raw = bytes(tx)
        _, decoded = e.packet(base64.b64encode(raw).decode())
        self.assertEqual(decoded, raw)
        corrupt = bytearray(raw)
        corrupt[2] ^= 1
        with self.assertRaises(Exception):
            e.packet(base64.b64encode(corrupt).decode())

    def test_per_leg_actual_amount_and_modeled_fee_not_promoted(self):
        row = {"venues": ["raydium_cpmm", "meteora_dlmm"], "pools": ["a", "b"],
               "source_slot": 10, "source_clock": {"slot": 11, "unix_timestamp": 100}}
        receipt = {"declared_first_leg_input_base_units": 100000,
                   "declared_second_leg_input_base_units": 1923,
                   "first_leg_intermediate_received_base_units": 1923,
                   "positive_post_balances_base_units": [0, 0, 97851]}
        quotes = [{"predicted_output_base_units": 1923, "quote_status": "SOURCE_BOUND_INDICATIVE"},
                  {"predicted_output_base_units": None, "quote_status": "NATIVE_QUOTE_SOURCE_DERIVED_NOT_EXACT",
                   "native_fee_envelope": {"lower_output_bound": 90000, "upper_output_bound": 100000,
                       "source_derived_dynamic_fee_quote": {"amount_out": 97850}}}]
        with patch("arb.fixture_all_venue_signed_quotes.quote_leg", side_effect=quotes) as mock:
            result = e.compare_models({}, row, receipt)
        self.assertEqual([call.kwargs["amount_in"] for call in mock.call_args_list], [100000, 1923])
        self.assertTrue(result["legs"][0]["exact_sample_amount_match"])
        self.assertEqual(result["legs"][1]["delta_base_units"], -1)
        self.assertTrue(result["legs"][1]["fee_envelope_contains_signed_output"])
        self.assertFalse(result["protocol_exact_verified"])
        self.assertFalse(result["legs"][0]["clock_same_slot"])


if __name__ == "__main__":
    unittest.main()
