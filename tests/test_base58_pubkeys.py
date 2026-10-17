import unittest
from arb.orca_whirlpool import b58
class Base58LeadingZeroTests(unittest.TestCase):
    def test_zero_pubkey(self):
        self.assertEqual(b58(bytes(32)),"1"*32)
    def test_leading_zero_pubkey(self):
        self.assertTrue(b58(bytes([0,1])+bytes(30)).startswith("1"))
    def test_known_system_key(self):
        self.assertEqual(b58(bytes([1])+bytes(31)),"4uQeVj5tqViQh7yWWGStvkEG1Zmhx6uasJtWCJziofM")
