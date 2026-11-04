import unittest
from arb.arbitrage_mission import check
class ArbitrageMissionTests(unittest.TestCase):
    def test_mission_checkpoint_is_present(self):
        self.assertTrue(check())
