import unittest
from unittest.mock import patch
from arb.verify_whirlpool import verify
from arb.orca_whirlpool import SOL, USDC

class PinnedPoolTests(unittest.TestCase):
    def test_empty_manifest_is_not_a_pass(self):
        with self.assertRaises(ValueError):
            verify("http://localhost:8899", [])

    @patch("arb.verify_whirlpool.fetch_pool")
    def test_expected_pair_and_liquidity(self, fetch):
        fetch.return_value = {"token_mint_a":SOL,"token_mint_b":USDC,"liquidity":"123"}
        self.assertEqual(len(verify("http://localhost:8899",[{"address":"example","verify_vaults":False}])),1)

    @patch("arb.verify_whirlpool.fetch_pool")
    def test_wrong_mints_rejected(self, fetch):
        fetch.return_value = {"token_mint_a":SOL,"token_mint_b":"other","liquidity":"123"}
        with self.assertRaises(ValueError):
            verify("http://localhost:8899",[{"address":"example","verify_vaults":False}])

    @patch("arb.verify_whirlpool.fetch_pool")
    def test_zero_liquidity_rejected(self, fetch):
        fetch.return_value = {"token_mint_a":SOL,"token_mint_b":USDC,"liquidity":"0"}
        with self.assertRaises(ValueError):
            verify("http://localhost:8899",[{"address":"example","verify_vaults":False}])
