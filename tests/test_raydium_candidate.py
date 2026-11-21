import unittest
from unittest.mock import patch
from arb.raydium_candidate import inspect
from arb.raydium_cpmm import PROGRAM
class DiagnosticTests(unittest.TestCase):
    @patch("arb.raydium_candidate.call",return_value={"value":None})
    def test_missing_not_verified(self,call):
        self.assertEqual(inspect("rpc","candidate")["status"],"MISSING")
    @patch("arb.raydium_candidate.call",return_value={"value":{"owner":"wrong"}})
    def test_other_program_not_verified(self,call):
        self.assertEqual(inspect("rpc","candidate")["status"],"WRONG_PROGRAM")
