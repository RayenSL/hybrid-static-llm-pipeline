import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import v04_analyze as an


class AnalysisTests(unittest.TestCase):
    def test_confirmatory_applies_holm_and_needs_the_interval_above_zero(self):
        report = an.confirmatory({'H3': [2, 1, 3, 1, 2, 1, 2, 1, 1, 2, 3, 1], 'H4': [1, -1, 0, 1, 0, -1, 1, 0, 0, 1, -1, 0]})
        self.assertTrue(report['H3']['supported'])
        self.assertFalse(report['H4']['supported'])
        self.assertGreaterEqual(report['H3']['p_holm'], report['H3']['p_one_sided'])

    def test_equivalence_uses_the_v04_sesoi(self):
        report = an.confirmatory({'H3': [0.1, -0.1, 0.0, 0.1, -0.1, 0.0], 'H4': [1.0, -1.0, 1.0, -1.0, 1.0, -1.0]})
        self.assertTrue(report['H3']['equivalent'])
        self.assertFalse(report['H4']['equivalent'])
        self.assertEqual(report['H3']['sesoi'], 0.5)

    def test_near_threshold_share_counts_owned_decisions_8_to_10(self):
        self.assertAlmostEqual(an.near_threshold_share({'A.a': 7, 'A.b': 8, 'A.c': 10, 'A.d': 11}, 8, 10), 0.5)
        self.assertIsNone(an.near_threshold_share({}, 8, 10))

    def test_gaming_verdict(self):
        self.assertEqual(an.gaming_verdict(accrual_ci90_upper=0.4, near_threshold_increase=0.05), 'debt_prevention')
        self.assertEqual(an.gaming_verdict(accrual_ci90_upper=1.5, near_threshold_increase=0.05), 'metric_suppression')
        self.assertEqual(an.gaming_verdict(accrual_ci90_upper=0.4, near_threshold_increase=0.2), 'metric_suppression')


if __name__ == '__main__':
    unittest.main()
