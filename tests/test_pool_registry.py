import unittest
from unittest.mock import patch
from arb.pool_registry import refresh
from arb.orca_whirlpool import SOL,USDC
class RegistryTests(unittest.TestCase):
    def test_committed_registry_hints_are_unique_and_non_executable(self):
        import json
        from pathlib import Path
        from arb.onchain_pool_discovery import VENUES
        registry=Path(__file__).resolve().parents[1]/"arb"/"pool_registry.json"
        entries=json.loads(registry.read_text())["pools"]
        self.assertLessEqual(len(entries),200)
        self.assertEqual(len(entries),
                         len({(e["venue"],e["address"]) for e in entries}))
        for entry in entries:
            self.assertIn(entry["venue"],VENUES)
            self.assertIsInstance(entry["address"],str)
            self.assertTrue(32 <= len(entry["address"]) <= 44)
            self.assertNotIn("actionable",entry)
            self.assertNotIn("verified",entry)
            if entry["venue"] == "pumpswap":
                self.assertEqual(len(entry["mints"]),2)
                self.assertEqual(len(set(entry["mints"])),2)

    def test_unbounded_rejected(self):
        with self.assertRaises(ValueError):refresh("rpc",[{}]*201)
    @patch("arb.pool_registry.verify")
    @patch("arb.pool_registry.call")
    @patch("arb.pool_registry.VENUES",{"test":("prog",3,0,0,lambda data:{"ok":True})})
    def test_revalidated_shared_pair(self,call,verify):
        import base64
        call.return_value={"value":{"owner":"prog","executable":False,
          "data":[base64.b64encode(b"abc").decode(),"base64"]}}
        def checked(rpc,venue,address,state):
            return {"venue":venue,"address":address,"mints":[SOL,USDC],
                    "slot":22,"vault_base_units":[100,200]}
        verify.side_effect=checked
        entries=[{"venue":"test","address":"a"*32}]
        result=refresh("rpc",entries)
        self.assertEqual(result["verified_count"],1)
        self.assertEqual(result["rejected_count"],0)
    @patch("arb.pool_registry.call",side_effect=RuntimeError("HTTP 429 too many requests"))
    def test_rate_limit_stops_repeated_source_reads(self,call):
        entries=[{"venue":"orca","address":str(i).zfill(40)} for i in range(4)]
        result=refresh("rpc",entries)
        self.assertEqual(result["status"],"UPSTREAM_RATE_LIMITED")
        self.assertEqual(result["rejected_count"],4)
        self.assertEqual(result["rejected"][-1]["reason"],"SKIPPED_UPSTREAM_RATE_LIMIT")
        call.assert_called_once()
    @patch("arb.pool_registry.call")
    def test_missing_pool_stays_rejected(self,call):
        call.return_value={"value":None}
        result=refresh("rpc",[{"venue":"orca","address":"1"*32}])
        self.assertEqual(result["verified_count"],0)
        self.assertEqual(result["status"],"PARTIAL")
        self.assertEqual(result["shared_pairs"],[])
