import unittest
from unittest.mock import patch
from arb.discover_onchain import discover

class OnchainDiscoveryTests(unittest.TestCase):
    @patch("arb.discover_onchain.call")
    def test_program_owner_verified(self, rpc_call):
        program = "ExampleProgram111"
        rpc_call.return_value = [{"pubkey":"CandidatePool1","account":{"owner":program,"executable":False}}]
        result = discover("http://127.0.0.1:8899", {"Test AMM":program}, max_accounts=5)
        self.assertEqual(result["programs"]["Test AMM"]["candidateCount"],1)
        self.assertEqual(result["programs"]["Test AMM"]["sampleAddresses"],["CandidatePool1"])
        self.assertEqual(rpc_call.call_args.args[1], "getProgramAccounts")

    @patch("arb.discover_onchain.call")
    def test_rejects_unowned_accounts(self, rpc_call):
        rpc_call.return_value = [{"pubkey":"Bad","account":{"owner":"other","executable":False}}]
        with self.assertRaises(ValueError):
            discover("http://127.0.0.1:8899",{"Test AMM":"Expected"})

    @patch("arb.discover_onchain.call")
    def test_rejects_unbounded_scan(self, rpc_call):
        rpc_call.return_value = [{"pubkey":str(i),"account":{"owner":"P","executable":False}} for i in range(4)]
        with self.assertRaises(ValueError):
            discover("http://127.0.0.1:8899",{"Test AMM":"P"},max_accounts=3)
