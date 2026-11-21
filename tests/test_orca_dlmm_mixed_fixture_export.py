import unittest
from unittest.mock import patch
from arb.orca_dlmm_mixed_fixture_export import require_route,export_mixed
from arb.orca_whirlpool import SOL

T="98sMhvw23FxCwYiz9YwvJdr9SaAZ6RfGmgxnSXnm9KBR"
def candidate(venues=("meteora_dlmm","orca"),tokens=None):
    tokens=tokens or [SOL,T,SOL]
    return {"tokens":tokens,"legs":[
        {"venue":venues[i],"pool":"pool"+str(i),"from":tokens[i],"to":tokens[i+1]}
        for i in range(2)]}

class OrcaDlmmFixtureSafetyTests(unittest.TestCase):
    def test_closed_two_leg_route_accepted(self):
        require_route(candidate())

    def test_nonclosing_and_repeated_venue_rejected(self):
        with self.assertRaises(ValueError):
            require_route(candidate(tokens=[SOL,T,T]))
        with self.assertRaises(ValueError):
            require_route(candidate(venues=("orca","orca")))

    @patch("arb.orca_dlmm_mixed_fixture_export.call")
    def test_missing_verified_candidate_never_reads_or_mutates(self,rpc):
        with self.assertRaisesRegex(ValueError,"no verified mixed target"):
            export_mixed("http://127.0.0.1:8899",{},"/tmp/notwritten.json")
        rpc.assert_not_called()

    @patch("arb.orca_dlmm_mixed_fixture_export.call")
    def test_remote_rpc_rejected_before_reading(self,rpc):
        with self.assertRaises(ValueError):
            export_mixed("https://api.mainnet-beta.solana.com",
                         {"first_dlmm_only_offline_target":candidate()},"/tmp/notwritten.json")
        rpc.assert_not_called()
