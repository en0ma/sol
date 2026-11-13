import unittest
from unittest.mock import patch
from arb.next_ten_signed_atomic_offline import run
class Tests(unittest.TestCase):
    def test_length_invalid_before_hydration(self):
        with self.assertRaisesRegex(ValueError,"adaptive hops must be 3-6"):
            run("http://127.0.0.1:8899",{},adaptive_hops=7)
    def test_mode_collision_rejected(self):
        with self.assertRaisesRegex(ValueError,"exactly one"):
            run("http://127.0.0.1:8899",{},adaptive_hops=4,adaptive_three_hop=True)
    def test_non_cpmm_v4_disallowed(self):
        with self.assertRaisesRegex(ValueError,"source"):
            run("http://127.0.0.1:8899",
                {"first_venue":"orca","second_venue":"raydium_cpmm"},adaptive_hops=5)
if __name__=="__main__":unittest.main()
