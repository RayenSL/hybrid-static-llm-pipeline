import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import replay_core as core


class ScheduleTests(unittest.TestCase):
    def test_branch_order_is_deterministic_permutation(self):
        branches = [('O', 1), ('O', 2), ('O', 3), ('R', 1)]
        first = core.branch_order('seed', 'T01', branches)
        self.assertEqual(first, core.branch_order('seed', 'T01', branches))
        self.assertEqual(sorted(first), sorted(branches))

    def test_branch_order_depends_on_target(self):
        branches = [('O', 1), ('O', 2), ('O', 3), ('R', 1)]
        orders = {tuple(core.branch_order('seed', f'T{i:02d}', branches)) for i in range(20)}
        self.assertGreater(len(orders), 1)


class DecodeTests(unittest.TestCase):
    def test_utf8_with_and_without_bom(self):
        self.assertEqual(core.decode_source('ä = 1;'.encode('utf-8')), 'ä = 1;')
        self.assertEqual(core.decode_source(b'\xef\xbb\xbf' + 'ä'.encode('utf-8')), 'ä')

    def test_windows_1252_fallback(self):
        self.assertEqual(core.decode_source('m² ¹'.encode('cp1252')), 'm² ¹')


class BudgetTests(unittest.TestCase):
    def test_reservation_scales_serialised_bytes(self):
        messages = [{'role': 'user', 'content': 'x' * 3500}]
        size = len(core.json.dumps(messages, ensure_ascii=False).encode('utf-8'))
        self.assertEqual(core.reservation(messages), math.ceil(size / 3.5 * 1.1) + 512)

    def test_may_call_requires_room_for_input_and_full_output(self):
        self.assertTrue(core.may_call(spent=100_000, reserve=50_000, max_output=4_096, allocation=160_000))
        self.assertFalse(core.may_call(spent=110_000, reserve=50_000, max_output=4_096, allocation=160_000))


class VerdictTests(unittest.TestCase):
    reference = {'A.t1': 'Passed', 'A.t2': 'Passed', 'A.flaky': 'Failed', 'Oracle.t': 'Passed'}
    f2p = {'A.t1', 'Oracle.t'}

    def verdict(self, candidate, build_ok=True, api_missing=(), within_allocation=True):
        return core.step_verdict(build_ok, list(api_missing), self.reference, self.f2p, candidate, within_allocation)

    def test_all_required_pass_completes(self):
        self.assertEqual(self.verdict({'A.t1': 'Passed', 'A.t2': 'Passed', 'A.flaky': 'Failed', 'Oracle.t': 'Passed'}), (True, None))

    def test_build_failure_dominates(self):
        self.assertEqual(self.verdict({}, build_ok=False, api_missing=['X.Y()']), (False, 'build'))

    def test_missing_api_member(self):
        self.assertEqual(self.verdict({'A.t1': 'Passed', 'A.t2': 'Passed', 'Oracle.t': 'Passed'}, api_missing=['X.Y()']), (False, 'api'))

    def test_fail_to_pass_before_regression(self):
        self.assertEqual(self.verdict({'A.t1': 'Failed', 'A.t2': 'Failed', 'Oracle.t': 'Passed'}), (False, 'fail_to_pass'))

    def test_regression_and_missing_test_count_as_failure(self):
        self.assertEqual(self.verdict({'A.t1': 'Passed', 'Oracle.t': 'Passed'}), (False, 'regression'))

    def test_reference_failures_are_not_required(self):
        self.assertEqual(self.verdict({'A.t1': 'Passed', 'A.t2': 'Passed', 'Oracle.t': 'Passed'}), (True, None))

    def test_allocation(self):
        self.assertEqual(self.verdict({'A.t1': 'Passed', 'A.t2': 'Passed', 'Oracle.t': 'Passed'}, within_allocation=False), (False, 'allocation'))


class TrajectoryTests(unittest.TestCase):
    def test_completed_prefix_stops_at_first_failure(self):
        self.assertEqual(core.completed_prefix([True, True, False, True]), 2)
        self.assertEqual(core.completed_prefix([]), 0)

    def test_accrual_per_change(self):
        self.assertEqual(core.accrual([100, 104, 110], 2), 5.0)
        self.assertIsNone(core.accrual([100, 104], 0))


class StatisticsTests(unittest.TestCase):
    def test_sign_flip_one_sided(self):
        self.assertEqual(core.sign_flip_greater([1, 1, 1]), 1 / 8)
        self.assertEqual(core.sign_flip_greater([1, -1]), 3 / 4)
        self.assertEqual(core.sign_flip_greater([0.5, 1.5]), 1 / 4)

    def test_t_interval(self):
        low, high = core.t_interval([1, 2, 3], 0.95)
        self.assertAlmostEqual(low, 2 - 4.302652729911275 / math.sqrt(3), places=6)
        self.assertAlmostEqual(high, 2 + 4.302652729911275 / math.sqrt(3), places=6)

    def test_holm(self):
        self.assertEqual(core.holm([0.01, 0.04]), [0.02, 0.04])
        self.assertEqual(core.holm([0.04, 0.03]), [0.06, 0.06])

    def test_kaplan_meier_recurrence(self):
        curve = core.kaplan_meier_recurrence([(1, True), (2, False), (2, True), (3, False)], horizon=3)
        self.assertAlmostEqual(curve[1], 0.25)
        self.assertAlmostEqual(curve[2], 0.5)
        self.assertAlmostEqual(curve[3], 0.5)

    def test_clopper_pearson(self):
        low, high = core.clopper_pearson(0, 10)
        self.assertEqual(low, 0.0)
        self.assertAlmostEqual(high, 0.30849710781876083, places=6)


if __name__ == '__main__':
    unittest.main()
