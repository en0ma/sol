import unittest
from unittest.mock import patch
from arb.orca_token2022_fee_boundaries import assess

A="So11111111111111111111111111111111111111112"
B="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
def state():
    cfg={"older":{"epoch":0,"basis_points":100,"maximum_fee":1000},
         "newer":{"epoch":4,"basis_points":200,"maximum_fee":1000}}
    return {"mints":[A,B],"slot":110,
            "epoch_observation":{"epoch":4},
            "mint_accounts":[{"transfer_fee_config":cfg},
                             {"transfer_fee_config":cfg}],
            "extension_risk":{"blocking_extension_ids":[1]}}

class OrcaToken2022FeeBoundariesTests(unittest.TestCase):
    @patch("arb.orca_token2022_fee_boundaries.epoch_anchored_snapshot")
    def test_two_transfer_boundaries_and_no_execution(self,snapshot):
        snapshot.return_value=state()
        result=assess("rpc","pool",A,101,100)
        self.assertEqual(result["pool_net_input_base_units"],98)
        self.assertEqual(result["recipient_net_output_base_units"],98)
        self.assertEqual(result["input_transfer_fee_base_units"],3)
        self.assertEqual(result["output_transfer_fee_base_units"],2)
        self.assertEqual(result["minimum_gross_for_observed_net"],100)
        self.assertFalse(result["amm_quote_verified"])
        self.assertFalse(result["transfer_hook_accounts_verified"])
        self.assertFalse(result["actionable"])
        snapshot.assert_called_once_with("rpc","pool")

    @patch("arb.orca_token2022_fee_boundaries.epoch_anchored_snapshot")
    def test_direction_uses_supplied_input_mint(self,snapshot):
        data=state()
        data["mint_accounts"][0]["transfer_fee_config"]=None
        snapshot.return_value=data
        result=assess("rpc","pool",B,100,100)
        self.assertEqual(result["pool_net_input_base_units"],98)
        self.assertEqual(result["recipient_net_output_base_units"],100)

    @patch("arb.orca_token2022_fee_boundaries.epoch_anchored_snapshot")
    def test_ambiguous_or_wrong_mint_rejected(self,snapshot):
        snapshot.return_value=state()
        with self.assertRaises(ValueError):
            assess("rpc","pool","unknown",100,100)
        with self.assertRaises(ValueError):
            assess("rpc","pool",A,-1,100)
