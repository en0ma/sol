import unittest
from arb.venue_capabilities import (complete_pair_matrix, SWAP_BUILDERS,
    ATOMIC_PAIR_EVIDENCE)

class PairwiseAtomicEvidenceTests(unittest.TestCase):
    def test_four_builders_produce_all_six_pairings(self):
        report=complete_pair_matrix()
        self.assertEqual(report["venue_count"],4)
        self.assertEqual(len(report["pairs"]),6)
        self.assertEqual(report["historical_verified_pairs"],3)
        self.assertEqual(len(ATOMIC_PAIR_EVIDENCE),3)
        self.assertFalse(report["current_ci_run_pair_simulated"])
        self.assertFalse(report["broadcast"])

    def test_builder_existence_not_evidence(self):
        report=complete_pair_matrix()
        pairs={frozenset(row["venues"]):row for row in report["pairs"]}
        missing=pairs[frozenset(("raydium_clmm","meteora_dlmm"))]
        self.assertTrue(missing["both_builders_available"])
        self.assertFalse(missing["historical_signed_atomic_pair_verified"])
        self.assertIsNone(missing["historical_atomic_evidence_artifact"])

    def test_directional_closed_cycle_is_not_symmetric(self):
        rows=complete_pair_matrix()["pairs"]
        pair=next(row for row in rows if set(row["venues"])=={"orca","meteora_dlmm"})
        orders=[tuple(item["order"]) for item in pair["closed_cycle_orders_verified"]]
        self.assertEqual(orders,[("meteora_dlmm","orca")])
        self.assertFalse(pair["arbitrary_pairing_approved"])
