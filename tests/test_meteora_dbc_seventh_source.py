"""Fail-closed DBC explicit-identity source tests; no network calls."""
import base64
import unittest
from unittest.mock import patch
from solders.pubkey import Pubkey
from arb.meteora_dbc_seventh_venue_source import (
    PROGRAM, DISC, authenticated_pool_hints,
)

ADDRESS = str(Pubkey.from_bytes(bytes([7]) * 32))


def reply(owner=PROGRAM, raw=DISC+b"test-payload", slot=123):
    return {"context": {"slot": slot}, "value": [{
        "owner": owner, "executable": False, "lamports": 1,
        "data": [base64.b64encode(raw).decode(), "base64"]
    }]}


class DbCExplicitSourceTests(unittest.TestCase):
    def test_authenticated_contextual_source_remains_unsigned(self):
        with patch("arb.meteora_dbc_seventh_venue_source.call", return_value=reply()) as rpc:
            entries = authenticated_pool_hints("https://readonly.example", [ADDRESS])
        self.assertEqual(entries[0]["address"], ADDRESS)
        self.assertEqual(entries[0]["source_slot"], 123)
        self.assertEqual(rpc.call_args.args[1], "getMultipleAccounts")

    def test_wrong_program_owner_rejected(self):
        with patch("arb.meteora_dbc_seventh_venue_source.call",
                   return_value=reply(owner=str(Pubkey.default()))):
            with self.assertRaisesRegex(ValueError, "authentication"):
                authenticated_pool_hints("https://readonly.example", [ADDRESS])

    def test_wrong_discriminator_rejected(self):
        with patch("arb.meteora_dbc_seventh_venue_source.call",
                   return_value=reply(raw=b"12345678bad")):
            with self.assertRaisesRegex(ValueError, "discriminator"):
                authenticated_pool_hints("https://readonly.example", [ADDRESS])

    def test_context_missing_fails_closed(self):
        with patch("arb.meteora_dbc_seventh_venue_source.call",
                   return_value={"value": reply()["value"]}):
            with self.assertRaisesRegex(ValueError, "contextual"):
                authenticated_pool_hints("https://readonly.example", [ADDRESS])

    def test_duplicate_addresses_rejected_before_rpc(self):
        with patch("arb.meteora_dbc_seventh_venue_source.call") as rpc:
            with self.assertRaisesRegex(ValueError, "distinct"):
                authenticated_pool_hints("https://readonly.example", [ADDRESS, ADDRESS])
            rpc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
