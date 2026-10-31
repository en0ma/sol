import unittest
from arb.quote_uncertainty import classify

class QuoteUncertaintyTests(unittest.TestCase):
    def test_reference_error_exceeds_tiny_gross(self):
        x=classify(247,111,100247)
        self.assertGreater(x["reference_error_buffer_base_units"],247)
        self.assertFalse(x["gross_exceeds_reference_error"])
        self.assertFalse(x["actionable"])

    def test_reference_does_not_certify_surviving_route(self):
        x=classify(5000,111,100000)
        self.assertTrue(x["gross_exceeds_reference_error"])
        self.assertFalse(x["simulation_verified"])

    def test_rejects_invalid_inputs(self):
        for args in ((True,111,1000),(1,-1,1000),(1,111,0)):
            with self.assertRaises(ValueError):classify(*args)
