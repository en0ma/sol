import unittest
from unittest.mock import patch
from arb.orca_legacy_owner_preflight import preflight,ORCA_TOKEN_SWAP_V1

A="58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2"
B="7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm"

class OrcaLegacyOwnerPreflightTests(unittest.TestCase):
    def test_empty_index_no_rpc(self):
        with patch("arb.orca_legacy_owner_preflight.call") as rpc:
            result=preflight("http://127.0.0.1:8899",[])
        rpc.assert_not_called()
        self.assertEqual(result["status"],"NO_INDEX_CANDIDATES")
        self.assertFalse(result["broadcast"])

    def test_batch_discards_whirlpool_and_missing_pool(self):
        response={"value":[{"owner":"whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
                            "executable":False},
                           {"owner":ORCA_TOKEN_SWAP_V1,"executable":False},None]}
        with patch("arb.orca_legacy_owner_preflight.call",return_value=response) as rpc:
            result=preflight("http://127.0.0.1:8899",[A,B,"1"*32,A])
        rpc.assert_called_once()
        self.assertEqual(result["matching_program"],[B])
        self.assertEqual(result["checked"],3)
        self.assertEqual(result["mismatched_owner"],1)
        self.assertEqual(result["missing"],1)
        self.assertFalse(result["onchain_pool_decoder_verified"])
        self.assertFalse(result["actionable"])
        self.assertFalse(result["live_execution_approved"])

    def test_64_candidates_are_screened_in_bounded_batches(self):
        def answer(rpc,method,params):
            self.assertEqual(method,"getMultipleAccounts")
            self.assertLessEqual(len(params[0]),16)
            return {"value":[{"owner":"whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc",
                              "executable":False} for _ in params[0]]}
        # Distinct synthetic keys exercise bounded batch sizing only.
        addresses=[("A"*30+format(i,"02d")) for i in range(64)]
        with patch("arb.orca_legacy_owner_preflight.call",side_effect=answer) as rpc:
            result=preflight("http://127.0.0.1:8899",addresses)
        self.assertEqual(rpc.call_count,4)
        self.assertEqual(result["checked"],64)
        self.assertEqual(result["mismatched_owner"],64)
        self.assertEqual(result["matching_program"],[])

    def test_incomplete_response_fails_closed(self):
        with patch("arb.orca_legacy_owner_preflight.call",return_value={"value":[]}):
            with self.assertRaisesRegex(ValueError,"incomplete"):
                preflight("http://127.0.0.1:8899",[A])

    def test_public_rpc_rejected(self):
        with patch("arb.orca_legacy_owner_preflight.call") as rpc:
            with self.assertRaises(ValueError):
                preflight("https://api.mainnet-beta.solana.com",[A])
        rpc.assert_not_called()

    def test_limits_rejected(self):
        with self.assertRaises(ValueError):
            preflight("http://127.0.0.1:8899",[A]*65)

if __name__=="__main__":
    unittest.main()
