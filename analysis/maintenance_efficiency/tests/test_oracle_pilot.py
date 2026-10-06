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


class PackageSourceTests(unittest.TestCase):
    CONFIG = ('<configuration><packageSources><clear />'
              '<add key="nuget" value="https://api.nuget.org/v3/index.json" />'
              r'<add key="Local" value="C:\LocalPackages" />'
              r'<add key="Share" value="\\server\feed" />'
              '<add key="Here" value="." />'
              '</packageSources></configuration>')

    def test_only_absolute_local_drive_sources_that_do_not_exist_are_listed(self):
        self.assertEqual(pilot.missing_local_sources(self.CONFIG, exists=lambda path: False), ['Local'])
        self.assertEqual(pilot.missing_local_sources(self.CONFIG, exists=lambda path: True), [])

    def test_missing_sources_are_added_as_disabled(self):
        text = pilot.nuget_config_disabling(['Local', 'Other'])
        self.assertIn('<add key="Local" value="true" />', text)
        self.assertIn('<add key="Other" value="true" />', text)
        self.assertIn('<add key="Infragistics" value="true" />', text)
        self.assertEqual(text.count('<disabledPackageSources>'), 1)


if __name__ == '__main__':
    unittest.main()
