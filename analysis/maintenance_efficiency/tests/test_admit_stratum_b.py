import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import admit_stratum_b as admit

# Step 2 cases: two acceptance, one regression; retained from step 1: S1-a (acceptance), S1-r (regression).
CASES = {'S2-a': True, 'S2-b': True, 'S2-r': False}
RETAINED = ['S1-a', 'S1-r']


def outcomes(passing):
    names = list(CASES) + RETAINED
    return {n: n in passing for n in names}


ALL = list(CASES) + RETAINED


class StepGateTests(unittest.TestCase):
    def test_well_formed_step_passes(self):
        result = {'previous': outcomes(['S2-r', 'S1-a', 'S1-r']), 'reference': outcomes(ALL),
                  'mutant1': outcomes([n for n in ALL if n != 'S2-b']), 'mutant2': outcomes([n for n in ALL if n != 'S2-r'])}
        self.assertEqual(admit.step_gates(2, CASES, RETAINED, set(), result), [])

    def test_g1_requirement_already_met(self):
        result = {'previous': outcomes(ALL), 'reference': outcomes(ALL), 'mutant1': outcomes([]), 'mutant2': outcomes([])}
        self.assertIn('G1', admit.step_gates(2, CASES, RETAINED, set(), result))

    def test_g2_reference_breaks_retained_case_unless_superseded(self):
        broken = outcomes([n for n in ALL if n != 'S1-r'])
        base = {'previous': outcomes(['S1-a', 'S1-r']), 'reference': broken, 'mutant1': outcomes([]), 'mutant2': outcomes([])}
        self.assertIn('G2', admit.step_gates(2, CASES, RETAINED, set(), base))
        self.assertNotIn('G2', admit.step_gates(2, CASES, RETAINED, {'S1-r'}, base))

    def test_g3_mutant_must_build_and_fail_a_step_case(self):
        result = {'previous': outcomes([]), 'reference': outcomes(ALL), 'mutant1': outcomes(ALL), 'mutant2': None}
        failed = admit.step_gates(2, CASES, RETAINED, set(), result)
        self.assertIn('G3:mutant1', failed)  # builds but catches nothing
        self.assertIn('G3:mutant2', failed)  # does not build

    def test_step_one_also_requires_repair_to_lack_requirement(self):
        cases = {'S1-a': True, 'S1-r': False}
        result = {'previous': {'S1-a': False, 'S1-r': True}, 'repaired': {'S1-a': True, 'S1-r': True},
                  'reference': {'S1-a': True, 'S1-r': True}, 'mutant1': {'S1-a': False, 'S1-r': True}, 'mutant2': {'S1-a': True, 'S1-r': False}}
        self.assertIn('G1', admit.step_gates(1, cases, [], set(), result))

    def test_author_check_without_repaired_outcomes_judges_g1_on_the_original_only(self):
        cases = {'S1-a': True, 'S1-r': False}
        result = {'previous': {'S1-a': False, 'S1-r': True}, 'reference': {'S1-a': True, 'S1-r': True},
                  'mutant1': {'S1-a': False, 'S1-r': True}, 'mutant2': {'S1-a': True, 'S1-r': False}}
        self.assertEqual(admit.step_gates(1, cases, [], set(), result), [])


class SequenceGateTests(unittest.TestCase):
    def test_g4_per_step_allows_steps_whose_tests_need_new_members_in_both(self):
        self.assertTrue(admit.g4([({'S1-a': False}, {'S1-a': False}), (None, None)]))
        self.assertFalse(admit.g4([({'S1-a': False}, {'S1-a': True}), (None, None)]))
        self.assertFalse(admit.g4([({'S1-a': False}, {'S1-a': False}), ({'S2-a': False}, None)]))
        self.assertFalse(admit.g4([(None, None)]))

    def test_case_names_unique_and_prefixed(self):
        self.assertEqual(admit.case_name_problems({1: ['S1-a'], 2: ['S2-a', 'S2-b']}), [])
        self.assertTrue(admit.case_name_problems({1: ['S1-a'], 2: ['S1-a']}))
        self.assertTrue(admit.case_name_problems({1: ['x']}))


if __name__ == '__main__':
    unittest.main()
