import unittest
from unittest.mock import patch
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from arb.orca_whirlpool import PROGRAM
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

    def test_absent_oracle_uses_derived_pda_without_claiming_initialized(self):
        signer = Keypair()
        pool = "94BpFoyri4uTT55NFSHKYNFyUMtoWXEisMA4LK7nTKPU"
        token22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
        token = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        mint_a = "So11111111111111111111111111111111111111112"
        mint_b = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        observed = {
            "structurally_verified": True, "address": pool,
            "pool": {"token_vault_a": str(Keypair().pubkey()),
                     "token_vault_b": str(Keypair().pubkey())},
            "mint_accounts": [{"owner": token22}, {"owner": token}],
            "mints": [mint_a, mint_b],
            "oracle_evidence": {"same_slot_verified": False, "address": None},
            "tick_arrays": [],
        }
        ticks = {"all_present": True, "addresses": [str(Keypair().pubkey()) for _ in range(3)]}
        with patch("arb.orca_swap_v2_fork_signed_attempt.directional_tick_array_candidates", return_value=ticks):
            instruction = prepare_authenticated_attempt(
                observed, signer, str(Keypair().pubkey()), str(Keypair().pubkey()))
        oracle = str(Pubkey.find_program_address(
            [b"oracle", bytes(Pubkey.from_string(pool))], Pubkey.from_string(PROGRAM))[0])
        self.assertEqual(str(instruction.accounts[-1].pubkey), oracle)
        observed["oracle_evidence"]["address"] = str(Keypair().pubkey())
        with patch("arb.orca_swap_v2_fork_signed_attempt.directional_tick_array_candidates", return_value=ticks):
            with self.assertRaisesRegex(ValueError, "oracle PDA"):
                prepare_authenticated_attempt(
                    observed, signer, str(Keypair().pubkey()), str(Keypair().pubkey()))
