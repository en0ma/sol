import unittest

from arb.token2022_transfer_amounts import (
    net_received, gross_required, transfer_adjusted_pair, MAX_U64)

def config(bps=100,cap=1000):
    schedule={"epoch":0,"basis_points":bps,"maximum_fee":cap}
    return {"older":schedule,"newer":schedule}

class Token2022TransferAmountsTests(unittest.TestCase):
    def test_rounding_and_both_transfer_boundaries(self):
        result=transfer_adjusted_pair(config(),config(200),0,101,100)
        self.assertEqual(result["input_transfer_fee_base_units"],2)
        self.assertEqual(result["pool_effective_input_base_units"],99)
        self.assertEqual(result["output_transfer_fee_base_units"],2)
        self.assertEqual(result["recipient_net_output_base_units"],98)
        self.assertFalse(result["amm_quote_verified"])
        self.assertFalse(result["actionable"])

    def test_inverse_exact_minimum_gross(self):
        expected=gross_required(config(100),0,100)
        self.assertEqual(expected["gross_base_units"],102)
        self.assertGreaterEqual(expected["net_base_units"],100)
        previous=net_received(config(100),0,101)
        self.assertLess(previous["net_base_units"],100)

    def test_capped_fee_and_full_percentage(self):
        x=gross_required(config(10000,10),0,11)
        self.assertEqual(x["gross_base_units"],21)
        self.assertEqual(x["fee_base_units"],10)
        with self.assertRaises(ValueError):
            gross_required(config(10000,MAX_U64),0,1)

    def test_absent_fee_config_and_boundary(self):
        self.assertEqual(gross_required(None,0,100)["gross_base_units"],100)
        self.assertEqual(net_received(None,0,0)["net_base_units"],0)
        for value in (-1,MAX_U64+1,1.5,True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                gross_required(None,0,value)
