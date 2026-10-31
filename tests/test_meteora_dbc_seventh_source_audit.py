"""Posthoc DBC raw provenance auditor regression tests."""
import base64
import hashlib
import unittest
from unittest.mock import patch

from solders.pubkey import Pubkey
from arb.meteora_dbc_seventh_state_capture import capture_pool
from arb.meteora_dbc_seventh_source_audit import independently_audit
from test_meteora_dbc_seventh_state_capture import raw_pool, context, pk


def report():
    raw=raw_pool()
    original={"address":pk(8),"account_base64":base64.b64encode(raw).decode(),
        "account_sha256":hashlib.sha256(raw).hexdigest(),"source_slot":100}
    with patch("arb.meteora_dbc_seventh_state_capture.call",return_value=context(raw)):
        row=capture_pool("https://readonly.invalid",original)
    return {"status":"DBC_ORIGINAL_CONTEXTUAL_SOURCE_PARTIAL_NOT_SIGNED",
       "source_pools":[row],"actionable":False,"broadcast":False,
       "signed_parity_verified":False}


class DbcIndependentSourceAuditTests(unittest.TestCase):
    def test_real_roles_and_clock_source_only_accepted(self):
        result=independently_audit(report())
        self.assertEqual(result["authenticated_source_pools"],1)
        self.assertFalse(result["signed_parity_verified"])
        self.assertFalse(result["native_pricing_verified"])

    def test_source_byte_tampering_rejected(self):
        r=report()
        account=r["source_pools"][0]["accounts"][pk(8)]
        raw=bytearray(base64.b64decode(account["account_base64"]))
        raw[232]^=1
        account["account_base64"]=base64.b64encode(raw).decode()
        with self.assertRaisesRegex(ValueError,"digest"):
            independently_audit(r)

    def test_false_signed_status_rejected(self):
        r=report();r["signed_parity_verified"]=True
        with self.assertRaisesRegex(ValueError,"unsigned source"):
            independently_audit(r)


if __name__=="__main__":unittest.main()
