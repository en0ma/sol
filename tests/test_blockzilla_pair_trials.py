"""Isolated pair selection and receipt gate regressions (not chain evidence)."""
import unittest
from solders.pubkey import Pubkey
from solders.signature import Signature
from arb import blockzilla_pair_trials as p


def key():
    return str(Pubkey.new_unique())


class PairTrialsTests(unittest.TestCase):
    def test_prefer_two_new_pools_and_both_rotations(self):
        a, b = key(), key()
        baseline = [{"venue": "orca", "address": key(), "mints": [a, b]}]
        new = [{"venue": v, "address": key(), "mints": [a, b], "source_verified_only": True,
                "historical_observation": {"slot": 10, "signature": "fixture"}}
               for v in ("raydium_cpmm", "meteora_dlmm")]
        routes = p.choose_pairs(baseline, new)
        self.assertEqual(len(routes), 4)
        self.assertTrue(all(r["novel_pool_count"] == 2 for r in routes))
        self.assertEqual({r["mints"][0] for r in routes}, {a,b})
        self.assertEqual(len({tuple(r["pools"]) for r in routes}), 2)
        self.assertTrue(all(r["shared_historical_observation"] for r in routes))
        with self.assertRaises(ValueError):
            p.choose_pairs(baseline, [{**new[0], "source_verified_only": False}])

    def test_receipt_exact_input_cpi_and_rollback_required(self):
        row = {"venues": ["raydium_cpmm","meteora_dlmm"], "pools": [key(),key()],
               "mints": [key(),key()], "source_slot": 10}
        row["mints"].append(row["mints"][0])
        fixture = {"state_account_manifest_sha256": "fixture"}
        receipt = {k: True for k in ("signed_transaction_verified", "instruction_order_verified",
            "signed_atomic_simulation_verified", "intermediate_intra_transaction_consumption_verified",
            "rollback_failure_case_verified", "failed_at_second_instruction_after_successful_first",
            "adaptive_second_input_verified_against_atomic_output", "signed_second_leg_consumes_full_first_output")}
        receipt.update(status="SIGNED_ATOMIC_AND_ROLLBACK_VERIFIED",
            execution_environment="ISOLATED_SURFPOOL_OFFLINE",
            route_pool_addresses=row["pools"], route_mints=row["mints"],
            first_venue=row["venues"][0], second_venue=row["venues"][1],
            state_account_manifest_sha256="fixture", state_accounts_observed_slot=10,
            second_leg_failure_instruction_index=1, declared_first_leg_input_base_units=p.AMOUNT,
            transaction_signature=str(Signature.default()),
            initial_balances_base_units=[p.AMOUNT,0,0],
            positive_post_balances_base_units=[0,0,p.AMOUNT-1],
            negative_persistent_balances_base_units=[p.AMOUNT,0,0], **p.SAFE)
        self.assertTrue(p.accepted_receipt(receipt,row,fixture))
        for patch in ({"rollback_failure_case_verified":False},
                      {"positive_post_balances_base_units":[1,0,2]},
                      {"state_accounts_observed_slot":11},
                      {"broadcast":True}):
            self.assertFalse(p.accepted_receipt({**receipt,**patch},row,fixture))


if __name__ == "__main__":
    unittest.main()
