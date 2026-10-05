import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import replay_analyze as analyze

# Series are metric values at state 0..j for each branch; H has every step.
TARGET = dict(
    H=dict(tokens=[1000, 1002, 1010], decisions=[50, 50, 51]),
    O1=dict(tokens=[1000, 1040, 1090], decisions=[50, 52, 55]),
    O2=dict(tokens=[1000, 1020], decisions=[50, 51]),
    O3=dict(tokens=[1000], decisions=[50]),
    R1=dict(tokens=[1200, 1220, 1230], decisions=[48, 48, 49]),
)


class ContrastTests(unittest.TestCase):
    def test_h1_is_mean_over_trajectories_with_matching_developer_steps(self):
        # O1: (1090-1000)/2 - (1010-1000)/2 = 40; O2: 20 - 2 = 18; O3 has no completed step.
        self.assertEqual(analyze.h1_difference(TARGET, 'tokens'), 29.0)

    def test_h1b_uses_decisions(self):
        # O1: 2.5 - 0.5 = 2; O2: 1 - 0 = 1.
        self.assertEqual(analyze.h1_difference(TARGET, 'decisions'), 1.5)

    def test_h2_pairs_first_trajectories_on_common_prefix(self):
        # j = min(2, 2) = 2: A_O1 = 2.5, A_R1 = 0.5.
        self.assertEqual(analyze.h2_difference(TARGET), 2.0)

    def test_no_completed_steps_gives_none(self):
        empty = dict(H=TARGET['H'], O1=dict(tokens=[1000], decisions=[50]), R1=dict(tokens=[1200], decisions=[48]))
        self.assertIsNone(analyze.h1_difference(empty, 'tokens'))
        self.assertIsNone(analyze.h2_difference(empty))

    def test_missing_repair_branch_excludes_target_from_h2(self):
        self.assertIsNone(analyze.h2_difference(dict(H=TARGET['H'], O1=TARGET['O1'])))


class ConfirmatoryTests(unittest.TestCase):
    def test_five_targets_cannot_reach_holm_significance(self):
        report = analyze.confirmatory({'H1': [5.0] * 5, 'H2': [5.0] * 5})
        self.assertFalse(report['H1']['supported'])

    def test_confirmatory_family_applies_holm(self):
        report = analyze.confirmatory({'H1': [30.0, 12.0, 8.0, 25.0, 40.0, 18.0], 'H2': [1.0, -1.0, 0.5, 0.0, 2.0, -0.5]})
        self.assertEqual(report['H1']['targets'], 6)
        self.assertAlmostEqual(report['H1']['p_one_sided'], 1 / 64)
        expected = analyze.core.holm([report['H1']['p_one_sided'], report['H2']['p_one_sided']])
        self.assertAlmostEqual(report['H1']['p_holm'], expected[0])
        self.assertAlmostEqual(report['H2']['p_holm'], expected[1])
        self.assertTrue(report['H1']['supported'])
        self.assertFalse(report['H2']['supported'])

    def test_none_values_are_counted_not_used(self):
        report = analyze.confirmatory({'H1': [10.0, None, 12.0], 'H2': [1.0, 2.0, None]})
        self.assertEqual(report['H1']['targets'], 2)
        self.assertEqual(report['H1']['without_completed_steps'], 1)


if __name__ == '__main__':
    unittest.main()
