"""Real-source DBC recent-transaction discovery: no synthetic acceptance."""
import base64
import unittest
from unittest.mock import patch

from solders.pubkey import Pubkey
from arb.meteora_dbc_seventh_recent_tx_discovery import discover
from arb.meteora_dbc_seventh_venue_source import DISC, PROGRAM


def key(n):
    return str(Pubkey.from_bytes(bytes([n])*32))


def rpc(method,params):
    if method=="getSignaturesForAddress":
        return [{"signature":"fake-transaction-hint","err":None}]
    if method=="getTransaction":
        return {"transaction":{"message":{"accountKeys":[PROGRAM,key(1),key(2)]}},
                "meta":{"loadedAddresses":{"writable":[],"readonly":[]}}}
    if method=="getMultipleAccounts":
        rows=[]
        for addr in params[0]:
            raw=DISC+bytes(416) if addr==key(1) else bytes(424)
            rows.append({"owner":PROGRAM if addr==key(1) else key(3),
                         "executable":False,"data":[base64.b64encode(raw).decode(),"base64"]})
        return {"context":{"slot":100},"value":rows}
    raise AssertionError(method)


class DbcRecentTransactionTests(unittest.TestCase):
    def test_original_program_owner_and_discriminator_required(self):
        with patch("arb.meteora_dbc_seventh_recent_tx_discovery.call",side_effect=rpc):
            result=discover("https://readonly.invalid",count=1)
        self.assertEqual(len(result["hints"]),1)
        self.assertEqual(result["hints"][0]["address"],key(1))
        self.assertEqual(result["authenticated_pricing_pools"],0)
        self.assertEqual(result["signed_verified_pools"],0)

    def test_invalid_context_rejected(self):
        def corrupted(method,params):
            r=rpc(method,params)
            if method=="getMultipleAccounts":del r["context"]
            return r
        with patch("arb.meteora_dbc_seventh_recent_tx_discovery.call",side_effect=corrupted):
            with self.assertRaisesRegex(ValueError,"context"):
                discover("https://readonly.invalid",count=1)

    def test_bounded_requests(self):
        with self.assertRaisesRegex(ValueError,"bounded"):
            discover("https://readonly.invalid",count=7)


if __name__=="__main__":
    unittest.main()
