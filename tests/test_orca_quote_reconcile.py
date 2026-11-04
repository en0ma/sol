import unittest
from arb.orca_quote_reconcile import compare_quote_and_simulation


class OrcaQuoteReconcileTests(unittest.TestCase):
    def evidence(self):
        q = {'status': 'INDICATIVE_MULTITICK_ONLY', 'actionable': False,
             'executable_quote': False, 'mint_in': 'WSOL', 'mint_out': 'USDC',
             'amount_in': 1000000, 'estimated_output_base_units': 1950}
        s = {'status': 'PASS', 'swap_success': True, 'program_invoked': True,
             'local_only': True, 'token_balance_changes': {
                 'input_mint': 'WSOL', 'output_mint': 'USDC',
                 'input_amount_base_units': 1000000,
                 'spent_base_units': 1000000, 'received_base_units': 1950}}
        return q, s

    def test_exact_balance_match_remains_non_actionable(self):
        q, s = self.evidence()
        result = compare_quote_and_simulation(q, s)
        self.assertEqual(result['status'], 'MATCH')
        self.assertEqual(result['absolute_error_base_units'], 0)
        self.assertFalse(result['executable_quote'])
        self.assertFalse(result['confirmed_profitable'])

    def test_nonzero_error_and_explicit_tolerance(self):
        q, s = self.evidence()
        s['token_balance_changes']['received_base_units'] = 1947
        self.assertEqual(compare_quote_and_simulation(q, s)['status'], 'MISMATCH')
        self.assertEqual(compare_quote_and_simulation(q, s, max_error_units=3)['status'], 'MATCH')

    def test_missing_simulation_and_partial_spend_fail_closed(self):
        for field, value in [('status', 'SIMULATION_FAILED'),
                             ('swap_success', False),
                             ('local_only', False),
                             ('program_invoked', False)]:
            with self.subTest(field=field):
                q, s = self.evidence()
                s[field] = value
                with self.assertRaises(ValueError):
                    compare_quote_and_simulation(q, s)
        q, s = self.evidence()
        s['token_balance_changes']['spent_base_units'] = 999999
        with self.assertRaises(ValueError):
            compare_quote_and_simulation(q, s)

    def test_mint_or_amount_mismatch_fails_closed(self):
        q, s = self.evidence()
        s['token_balance_changes']['output_mint'] = 'RAY'
        with self.assertRaises(ValueError):
            compare_quote_and_simulation(q, s)
        q, s = self.evidence()
        q['amount_in'] = 2000000
        with self.assertRaises(ValueError):
            compare_quote_and_simulation(q, s)
