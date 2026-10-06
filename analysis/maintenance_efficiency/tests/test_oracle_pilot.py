import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import oracle_pilot as pilot


def row(stratum, build, tests):
    return dict(stratum=stratum, solution_built=build, test_projects=tests)


def project(status, passed=0, failed=0):
    return dict(status=status, passed=passed, failed=failed)


class OracleTests(unittest.TestCase):
    def test_oracle_needs_a_built_solution_and_a_project_with_enough_passing_tests(self):
        self.assertTrue(pilot.has_oracle(row('x', True, [project('ran', passed=25)])))
        self.assertFalse(pilot.has_oracle(row('x', False, [project('ran', passed=25)])))
        self.assertFalse(pilot.has_oracle(row('x', True, [project('ran', passed=9)])))
        self.assertFalse(pilot.has_oracle(row('x', True, [project('build_failed')])))
        self.assertFalse(pilot.has_oracle(row('x', True, [])))

    def test_passing_tests_are_summed_over_projects(self):
        self.assertTrue(pilot.has_oracle(row('x', True, [project('ran', passed=6), project('ran', passed=6)])))

    def test_yield_by_stratum(self):
        rows = [row('a', True, [project('ran', passed=30)]), row('a', False, []), row('b', True, [project('ran', passed=30)])]
        self.assertEqual(pilot.yield_by_stratum(rows), {'a': dict(checked=2, with_oracle=1), 'b': dict(checked=1, with_oracle=1)})


if __name__ == '__main__':
    unittest.main()
