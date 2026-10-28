import unittest
from arb.pumpswap_source_fee_envelope import quote_component_rounding_scenarios

class NativePumpSwapSourceFeeRoundingTests(unittest.TestCase):
    def test_integer_fee_component_rounding_scenarios(self):
        data=quote_component_rounding_scenarios(
            amount_in=1001,reserve_in=1000000,reserve_out=2000000,
            component_fee_bps=[15,5,1])
        self.assertEqual(data["aggregate_ceiling_fee_units"],3)
        self.assertEqual(data["aggregate_floor_fee_units"],2)
        self.assertEqual(data["component_ceiling_fee_units"],4)
        self.assertEqual(len(data["modeled_outputs"]),3)
        self.assertLessEqual(data["minimum_modeled_output_base_units"],
                             data["maximum_modeled_output_base_units"])
        self.assertFalse(data["protocol_exact_verified"])
        self.assertFalse(data["broadcast"])

    def test_source_output_liquidity_limit_is_strict(self):
        with self.assertRaisesRegex(ValueError,"cannot"):
            quote_component_rounding_scenarios(
                amount_in=500000,reserve_in=1000,reserve_out=2000,
                component_fee_bps=[10,10,10],
                output_liquidity_cap=1)

    def test_excessive_or_negative_fee_component_rejected(self):
        for fees in ([10000,0,0],[200,-1,0],[10,10],["1",2,3]):
            with self.subTest(fees=fees):
                with self.assertRaises(ValueError):
                    quote_component_rounding_scenarios(
                        amount_in=1000,reserve_in=10000,reserve_out=20000,
                        component_fee_bps=fees)

    def test_model_never_reports_verified_profitable_execution(self):
        result=quote_component_rounding_scenarios(
            amount_in=100000,reserve_in=10000000,reserve_out=5000000,
            component_fee_bps=[20,5,10])
        self.assertFalse(result["effective_fee_rounding_verified"])
        self.assertNotIn("net_profit_verified",result)
        self.assertNotIn("actionable_opportunity",result)
