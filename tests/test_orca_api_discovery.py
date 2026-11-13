import unittest
from unittest.mock import patch
from arb.orca_api_discovery import parse_page, scan

A="7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm"
B="5sgXhG1c9VBceg6aVQguK3NnbPfHinERZj86As6zW5Be"
C="27ZbVdmoUhG639CfqG6kW8a4VXZeGBi8Dd4HUXjVDxeS"

class OrcaApiDiscoveryTests(unittest.TestCase):
    def test_untrusted_addresses_only_and_cursor(self):
        entries,cursor=parse_page({"data":[{"address":A,"price":"999999"},
            {"address":A},{"address":"bad"}],"meta":{"next":"next-page"}})
        self.assertEqual(len(entries),1)
        self.assertEqual(cursor,"next-page")
        self.assertEqual(entries[0]["address"],A)
        self.assertFalse(entries[0]["verified"])
        self.assertNotIn("price",entries[0])

    def test_invalid_response_fails_closed(self):
        for data in ({"data":[]},{"data":{},"meta":{}},
                     {"data":[],"meta":{"next":5}},
                     {"data":[],"meta":{"next":"x"*2049}}):
            with self.subTest(data=data),self.assertRaises(ValueError):
                parse_page(data)

    @patch("arb.orca_api_discovery.refresh_batched")
    @patch("arb.orca_api_discovery.fetch_page")
    def test_new_addresses_independently_validated(self,fetch,validate):
        fetch.side_effect=[{"data":[{"address":A},{"address":B}],
                            "meta":{"next":"cursor"}},
                           {"data":[{"address":B},{"address":C}],
                            "meta":{"next":None}}]
        validate.return_value={"verified_count":1,"rejected_count":1,
            "batch_count":1,"verified_pools":[{"venue":"orca","address":B,
            "mints":["mint1","mint2"]}],
            "rejected":[{"address":C,"reason":"onchain verification failed"}]}
        report=scan("rpc",pinned=[A],pages=2,size=2,min_tvl=0,limit=20)
        self.assertEqual(report["candidate_count"],3)
        self.assertEqual(report["new_candidate_count"],2)
        self.assertEqual(report["new_verified_count"],1)
        self.assertEqual([e["address"] for e in validate.call_args.args[1]],[B,C])
        self.assertFalse(report["actionable"])
        self.assertEqual(fetch.call_count,2)

    @patch("arb.orca_api_discovery.refresh_batched")
    @patch("arb.orca_api_discovery.fetch_page")
    def test_no_indexer_results_does_not_invent_pools(self,fetch,validate):
        fetch.return_value={"data":[],"meta":{"next":None}}
        validate.return_value={"verified_count":0,"rejected_count":0,
                               "batch_count":0,"verified_pools":[],"rejected":[]}
        result=scan("rpc")
        self.assertEqual(result["new_verified_count"],0)
        self.assertEqual(result["checked_count"],0)

    @patch("arb.orca_api_discovery.fetch_page")
    def test_repeating_page_cursor_fails_closed(self,fetch):
        fetch.return_value={"data":[],"meta":{"next":"repeat"}}
        with self.assertRaisesRegex(ValueError,"repeated"):
            scan("rpc",pages=3)

    def test_invalid_budget(self):
        with self.assertRaises(ValueError):
            scan("rpc",pages=11)
