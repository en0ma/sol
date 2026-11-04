import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arb.damm_v2_isolated_execution import export, offline, SAFETY, PROGRAM


class IsolatedDammV2Tests(unittest.TestCase):
    def test_export_rejects_nonlocal_rpc_without_any_rpc_reads(self):
        with patch("arb.damm_v2_isolated_execution.call") as rpc:
            with self.assertRaises(ValueError):
                export("https://api.mainnet-beta.solana.com", "/dev/null")
            rpc.assert_not_called()

    def test_export_fails_closed_on_mismatched_pool_owner(self):
        with patch("arb.damm_v2_isolated_execution.call",
                   return_value={"value": {"owner": "wrong"}}) as rpc:
            with self.assertRaisesRegex(ValueError, "pool unavailable"):
                export("http://localhost:8899", "/dev/null")
            self.assertEqual(rpc.call_count, 1)
            self.assertEqual(rpc.call_args.args[1], "getAccountInfo")

    def test_offline_requires_explicit_opt_in_before_fixture_read(self):
        with patch.dict(os.environ, {"SURFPOOL_EXPLICITLY_OFFLINE": "0"}):
            with patch("arb.damm_v2_isolated_execution.call") as rpc:
                with self.assertRaisesRegex(ValueError, "offline Surfpool"):
                    offline("http://localhost:8899", "/no/such/fixture", "/dev/null")
                rpc.assert_not_called()

    def test_offline_rejects_untrusted_fixture_before_any_write(self):
        with tempfile.TemporaryDirectory() as root:
            fixture = Path(root) / "fixture.json"
            output = Path(root) / "evidence.json"
            fixture.write_text(json.dumps({"source": "UNTRUSTED"}))
            with patch.dict(os.environ, {"SURFPOOL_EXPLICITLY_OFFLINE": "1"}):
                with patch("arb.damm_v2_isolated_execution.call") as rpc:
                    with self.assertRaisesRegex(ValueError, "provenance"):
                        offline("http://localhost:8899", str(fixture), str(output))
                    rpc.assert_not_called()
            evidence = json.loads(output.read_text())
            self.assertEqual(evidence["status"], "UNVERIFIED")
            self.assertIs(evidence["signed_standalone_simulation_verified"], False)
            for key, value in SAFETY.items():
                self.assertIs(evidence[key], value)


if __name__ == "__main__":
    unittest.main()
