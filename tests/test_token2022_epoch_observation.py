import unittest
from unittest.mock import patch
from arb.token2022_epoch_observation import epoch_anchored_snapshot

def checked(slot=101):
    return {"slot":slot,"mint_accounts":[
        {"transfer_fee_config":{"older":{"epoch":1,"basis_points":30,"maximum_fee":20},
                                "newer":{"epoch":5,"basis_points":100,"maximum_fee":50}}},
        {"transfer_fee_config":None}],"actionable":False}

class EpochObservationTests(unittest.TestCase):
    @patch("arb.token2022_epoch_observation.snapshot")
    @patch("arb.token2022_epoch_observation.call")
    def test_fee_schedule_uses_bracketed_epoch(self, rpc, snapshot):
        snapshot.return_value=checked()
        rpc.side_effect=[{"epoch":5,"absoluteSlot":100},
                         {"epoch":5,"absoluteSlot":102}]
        result=epoch_anchored_snapshot("rpc","pool")
        self.assertEqual(result["mint_fee_schedules"][0]["basis_points"],100)
        self.assertEqual(result["mint_fee_schedules"][0]["maximum_fee"],50)
        self.assertFalse(result["effective_fee_verified"])
        self.assertFalse(result["actionable"])
        snapshot.assert_called_once_with("rpc","pool",min_context_slot=100)

    @patch("arb.token2022_epoch_observation.snapshot")
    @patch("arb.token2022_epoch_observation.call")
    def test_crossing_epoch_boundary_fails_closed(self,rpc,snapshot):
        snapshot.return_value=checked()
        rpc.side_effect=[{"epoch":4,"absoluteSlot":100},
                         {"epoch":5,"absoluteSlot":102}]
        with self.assertRaisesRegex(ValueError,"bracket"):
            epoch_anchored_snapshot("rpc","pool")

    @patch("arb.token2022_epoch_observation.snapshot")
    @patch("arb.token2022_epoch_observation.call")
    def test_snapshot_outside_slot_window_fails_closed(self,rpc,snapshot):
        snapshot.return_value=checked(slot=200)
        rpc.side_effect=[{"epoch":5,"absoluteSlot":100},
                         {"epoch":5,"absoluteSlot":102}]
        with self.assertRaisesRegex(ValueError,"bracket"):
            epoch_anchored_snapshot("rpc","pool")

    @patch("arb.token2022_epoch_observation.snapshot")
    @patch("arb.token2022_epoch_observation.call")
    def test_unbounded_window_fails_closed(self,rpc,snapshot):
        snapshot.return_value=checked(slot=110)
        rpc.side_effect=[{"epoch":5,"absoluteSlot":100},
                         {"epoch":5,"absoluteSlot":140}]
        with self.assertRaisesRegex(ValueError,"too wide"):
            epoch_anchored_snapshot("rpc","pool")
