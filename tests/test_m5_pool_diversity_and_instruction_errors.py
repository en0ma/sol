"""Pool-coverage selection and Solana instruction diagnostics regression tests."""
import unittest
from collections import deque
from arb.m5_three_hop_atomic_inventory import choose_pool_diverse_candidate, failed_instruction_context


class PoolCoverageSelectionTests(unittest.TestCase):
    def test_prefers_unseen_pools_to_first_lexicographic_route(self):
        route_a={"legs":[{"venue":"orca","pool":"already"},
                         {"venue":"raydium_cpmm","pool":"known"},
                         {"venue":"meteora_dlmm","pool":"known2"}]}
        route_b={"legs":[{"venue":"orca","pool":"fresh"},
                         {"venue":"raydium_cpmm","pool":"fresh2"},
                         {"venue":"meteora_dlmm","pool":"fresh3"}]}
        choices=deque([("first",route_a),("second",route_b)])
        choice=choose_pool_diverse_candidate(choices,set(),
            {("orca","already"),("raydium_cpmm","known"),("meteora_dlmm","known2")})
        self.assertEqual(choice[0],"second")
        self.assertEqual(len(choices),1)
        self.assertEqual(choices[0][0],"first")

    def test_preserves_identity_dedup(self):
        route={"legs":[{"venue":"orca","pool":"a"}]}
        choices=deque([("seen",route),("available",route)])
        self.assertEqual(choose_pool_diverse_candidate(choices,{"seen"},set())[0],"available")
        self.assertIsNone(choose_pool_diverse_candidate(choices,{"seen"},set()))

    def test_instruction_error_attributes_actual_leg(self):
        row={"venues":["orca","meteora_dlmm","raydium_clmm"],
             "pools":["pool0","pool1","pool2"]}
        self.assertEqual(failed_instruction_context(row,
            "ValueError: signed prefix simulation failed: {'InstructionError': [1, {'Custom': 6042}]}"),
            {"failed_instruction_index":1,"program_error_code":6042,
             "failed_venue":"meteora_dlmm","failed_pool":"pool1",
             "program_error_name":"PoolDisabled",
             "diagnostic_class":"DLMM_SWAP_BLOCKED_BY_POOL_STATUS_OR_ACTIVATION"})
        self.assertEqual(failed_instruction_context(row,
            "{'InstructionError': [2, {'Custom': 6042}]}"),
            {"failed_instruction_index":2,"program_error_code":6042,
             "failed_venue":"raydium_clmm","failed_pool":"pool2"})
        self.assertEqual(failed_instruction_context(row,"other error"),{})


if __name__=="__main__":
    unittest.main()
