import unittest
from unittest.mock import patch
from solders.keypair import Keypair
from arb.orca_swap_v2_fork_signed_attempt import prepare_authenticated_attempt, run

class ForkSwapAttemptTests(unittest.TestCase):
    def test_missing_authenticated_snapshot_rejected(self):
        with self.assertRaisesRegex(ValueError, "authenticated"):
            prepare_authenticated_attempt({}, Keypair(), "a", "b")

    def test_missing_directional_tick_evidence_rejected(self):
        snapshot = {"structurally_verified": True, "pool": {"tick_spacing": 64, "tick_current_index": 0},
                    "mint_accounts": [{"owner": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"}] * 2,
                    "tick_arrays": []}
        with self.assertRaisesRegex(ValueError, "tick arrays incomplete"):
            prepare_authenticated_attempt(snapshot, Keypair(), "a", "b")

    def test_read_only_attempt_never_fabricates_success(self):
        with patch("arb.orca_swap_v2_fork_signed_attempt.snapshot",
                   side_effect=ValueError("pool not accessible")):
            report = run("http://127.0.0.1:8899")
        self.assertEqual(report["status"], "SIGNED_SWAPV2_ATTEMPT_BLOCKED")
        self.assertFalse(report["signed_simulation_verified"])
        self.assertFalse(report["broadcast"])

    def test_nonloopback_is_rejected(self):
        with self.assertRaises(ValueError):
            run("https://api.mainnet-beta.solana.com")
