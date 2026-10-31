import unittest
from unittest.mock import patch
from arb.token2022_epoch_observation import _scheduled_epoch,scheduled_epoch_snapshot

SCHEDULE={"slotsPerEpoch":100,"firstNormalSlot":0,"firstNormalEpoch":0}
def state(slot=1005):
    return {"slot":slot,"mint_accounts":[
        {"transfer_fee_config":{"older":{"epoch":0,"basis_points":25,"maximum_fee":50},
                                "newer":{"epoch":10,"basis_points":100,"maximum_fee":40}}},
        {"transfer_fee_config":None}],"actionable":False}

class ScheduledEpochTests(unittest.TestCase):
    def test_epoch_from_snapshot_slot(self):
        self.assertEqual(_scheduled_epoch(1005,SCHEDULE),10)
        with self.assertRaises(ValueError):
            _scheduled_epoch(9,{"slotsPerEpoch":100,"firstNormalSlot":10,"firstNormalEpoch":1})

    @patch("arb.token2022_epoch_observation.snapshot")
    @patch("arb.token2022_epoch_observation.call")
    def test_fork_epoch_head_ahead_one_slot_is_allowed_for_read_only(self,call,snapshot):
        snapshot.return_value=state()
        call.side_effect=[SCHEDULE,{"epoch":10,"absoluteSlot":1006}]
        result=scheduled_epoch_snapshot("rpc","pool")
        self.assertEqual(result["epoch_observation"]["epoch"],10)
        self.assertEqual(result["mint_fee_schedules"][0]["basis_points"],100)
        self.assertFalse(result["executable_quote"])
        snapshot.assert_called_once_with("rpc","pool")

    @patch("arb.token2022_epoch_observation.snapshot")
    @patch("arb.token2022_epoch_observation.call")
    def test_epoch_boundary_crossing_rejected(self,call,snapshot):
        snapshot.return_value=state(slot=999)
        call.side_effect=[SCHEDULE,{"epoch":10,"absoluteSlot":1000}]
        with self.assertRaisesRegex(ValueError,"boundary"):
            scheduled_epoch_snapshot("rpc","pool")

    @patch("arb.token2022_epoch_observation.snapshot")
    @patch("arb.token2022_epoch_observation.call")
    def test_inconsistent_rpc_epoch_rejected(self,call,snapshot):
        snapshot.return_value=state()
        call.side_effect=[SCHEDULE,{"epoch":9,"absoluteSlot":1006}]
        with self.assertRaisesRegex(ValueError,"conflicts"):
            scheduled_epoch_snapshot("rpc","pool")
