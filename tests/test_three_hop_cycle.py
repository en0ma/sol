import unittest
from arb.three_hop_cycle import check_balances
class CycleBalanceTests(unittest.TestCase):
    def test_missing_post_accounts_rejected(self):
        with self.assertRaises(ValueError):
            check_balances({"accounts":[]},["a","b","c"],["wsol","usdc","ray"])
