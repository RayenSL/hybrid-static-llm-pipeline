import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import replay_prepare as prep

RECORD = {
    'post': {'P.Tests': {'status': 'ran', 'outcomes': {'a': 'Passed', 'b': 'Passed', 'c': 'Failed'}},
             'Q.Tests': {'status': 'no_tests', 'outcomes': {}}},
    'pre': {'x.cs': {'P.Tests': {'status': 'ran', 'outcomes': {'a': 'Failed', 'b': 'Passed', 'c': 'Failed'}}},
            'y.cs': {'P.Tests': {'status': 'build_failed', 'outcomes': {}}}},
    'stub': {'y.cs': {'stubbed': ['Y.M()'], 'P.Tests': {'status': 'ran', 'outcomes': {'a': 'Passed', 'b': 'Failed', 'c': 'Failed'}}}},
}


class PrepareTests(unittest.TestCase):
    def test_developer_fail_to_pass_from_pre_file(self):
        self.assertEqual(prep.developer_fail_to_pass(RECORD, 'x.cs', set()), {'P.Tests::a'})

    def test_developer_fail_to_pass_from_stub_when_pre_does_not_build(self):
        self.assertEqual(prep.developer_fail_to_pass(RECORD, 'y.cs', set()), {'P.Tests::b'})

    def test_excluded_projects_contribute_nothing(self):
        self.assertEqual(prep.developer_fail_to_pass(RECORD, 'x.cs', {'P.Tests'}), set())

    def test_reference_outcomes_skip_excluded_and_unrun_projects(self):
        self.assertEqual(prep.reference_outcomes(RECORD, set()), {'P.Tests': {'a': 'Passed', 'b': 'Passed', 'c': 'Failed'}})

    def test_qualified_names_flatten_projects(self):
        self.assertEqual(prep.qualified({'P.Tests': {'a': 'Passed'}, 'oracle/T01S1': {'a': 'Failed'}}),
                         {'P.Tests::a': 'Passed', 'oracle/T01S1::a': 'Failed'})

    def test_qualifying_prefix(self):
        self.assertEqual(prep.qualifying_prefix(['test', 'unchecked', 'stub'], [False, True, False]), 3)
        self.assertEqual(prep.qualifying_prefix(['stub', 'unchecked', 'stub'], [False, False, False]), 1)
        self.assertEqual(prep.qualifying_prefix(['unchecked', 'stub'], [False, False]), 0)

    def test_contiguous_prefix_ends_where_a_step_parent_differs_from_the_previous_state(self):
        self.assertEqual(prep.contiguous_prefix(['t0', 's1', 'merged'], ['t0', 's1', 's2']), 2)
        self.assertEqual(prep.contiguous_prefix(['t0', 's1'], ['t0', 's1']), 2)
        self.assertEqual(prep.contiguous_prefix(['x'], ['t0']), 0)

    def test_calibration_draws_god_class_targets_by_hash(self):
        targets = [dict(target_id=f'T{i:02d}', type='godClass' if i % 2 else 'longMethod') for i in range(1, 9)]
        chosen = prep.select_calibration(targets, 'seed', 2)
        self.assertEqual(len(chosen), 2)
        self.assertTrue(all(t['type'] == 'godClass' for t in targets if t['target_id'] in chosen))
        self.assertEqual(chosen, prep.select_calibration(list(reversed(targets)), 'seed', 2))


if __name__ == '__main__':
    unittest.main()
