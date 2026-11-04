import unittest
from pathlib import Path
from arb.damm_cpmm_atomic_offline import run_reverse, run, DAMM, CPMM

class ReverseAtomicRunnerTests(unittest.TestCase):
    def test_reverse_has_independent_entry_point(self):
        self.assertIsNot(run_reverse,run)
    def test_invalid_amounts_rejected_before_fork_mutation(self):
        from unittest.mock import patch
        with patch.dict("os.environ",{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
            with patch("arb.damm_cpmm_atomic_offline.call") as rpc:
                with self.assertRaises(ValueError):
                    run_reverse("http://localhost:8899",{},first_input=0)
                rpc.assert_not_called()
    def test_remote_endpoint_refused(self):
        from unittest.mock import patch
        with patch("arb.damm_cpmm_atomic_offline.call") as rpc:
            with self.assertRaises(ValueError):
                run_reverse("https://api.mainnet-beta.solana.com",{})
            rpc.assert_not_called()
if __name__=="__main__":
    unittest.main()
