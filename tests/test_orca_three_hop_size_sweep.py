import os
import unittest
from unittest.mock import patch
from arb.orca_three_hop_offline_simulation import hydrate_and_simulate, TEST_SIZES

class OfflineSizeSweepSafetyTests(unittest.TestCase):
    def test_bounded_sizes(self):
        self.assertEqual(TEST_SIZES,(100000,1000000,5000000))
        self.assertEqual(len(set(TEST_SIZES)),3)

    @patch.dict(os.environ,{"SURFPOOL_EXPLICITLY_OFFLINE":"1"})
    def test_negative_and_excessive_size_rejected_before_mutation(self):
        with patch("arb.orca_three_hop_offline_simulation.call") as rpc:
            for size in (-1,0,100000001,True):
                with self.subTest(size=size):
                    with self.assertRaisesRegex(ValueError,"bounded positive input"):
                        hydrate_and_simulate("http://127.0.0.1:8899",{},size)
            rpc.assert_not_called()

    @patch.dict(os.environ,{},clear=True)
    def test_no_offline_flag_blocks_all_size_sweeps(self):
        with patch("arb.orca_three_hop_offline_simulation.call") as rpc:
            with self.assertRaisesRegex(ValueError,"offline fixture writes prohibited"):
                hydrate_and_simulate("http://127.0.0.1:8899",{},1000000)
            rpc.assert_not_called()
