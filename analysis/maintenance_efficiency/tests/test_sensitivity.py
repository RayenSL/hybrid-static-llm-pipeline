import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import sensitivity as sens


class SensitivityTests(unittest.TestCase):
    def test_a_target_is_retried_when_any_step_made_a_second_call(self):
        self.assertTrue(sens.retried([dict(calls=[{}]), dict(calls=[{}, {}])]))
        self.assertFalse(sens.retried([dict(calls=[{}]), dict(calls=[{}])]))

    def test_h2_on_full_prefixes_uses_each_branch_own_length(self):
        series = {'O1': dict(decisions=[10, 12, 14]), 'R1': dict(decisions=[10, 11, 12, 16])}
        self.assertAlmostEqual(sens.h2_full_prefix(series), 2.0 - 2.0)
        self.assertIsNone(sens.h2_full_prefix({'O1': dict(decisions=[10, 12])}))

    def test_missing_differences_are_imputed_at_the_observed_extremes(self):
        self.assertEqual(sens.impute([1.0, None, -2.0, 3.0], 'best'), [1.0, 3.0, -2.0, 3.0])
        self.assertEqual(sens.impute([1.0, None, -2.0, 3.0], 'worst'), [1.0, -2.0, -2.0, 3.0])

    def test_censored_branches_count_as_recurred_only_in_the_worst_case(self):
        rows = [dict(recurred=False, censored=True), dict(recurred=True, censored=False), dict(recurred=False, censored=False)]
        self.assertEqual(sens.p1_bounds(rows), dict(best=dict(recurred=1, n=3), worst=dict(recurred=2, n=3)))

    def test_recurrence_counts_only_when_the_symbol_owns_more_decisions_than_at_step_0(self):
        self.assertTrue(sens.grew({'A.M': 8}, {'A.M': 11}, 'A.M'))
        self.assertFalse(sens.grew({'A.M': 11}, {'A.M': 11}, 'A.M'))
        self.assertTrue(sens.grew({}, {'A.M': 11}, 'N.A.M'))


if __name__ == '__main__':
    unittest.main()
