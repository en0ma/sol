import unittest
from arb.raydium_clmm_execution import check_balances
class CLMMExecutionTests(unittest.TestCase):
    def test_missing_simulation_accounts_fails(self):
        with self.assertRaises(ValueError):
            check_balances({"accounts":[]},["one","two","three"],["a","b","c"])
