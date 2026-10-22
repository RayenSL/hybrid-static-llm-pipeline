import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import v05_run as v05

PATH = 'Ibis.Calculeren/BL/Widget.cs'


def finding(kind, symbol, path='BL\\Widget.cs', cc=12):
    return dict(type=kind, symbolName=symbol, filePath=path, line=10, metrics=dict(CyclomaticComplexity=cc))


UNIT = ['Widget.Big']
BEFORE = [finding('longMethod', 'Widget.Big'), finding('longMethod', 'Widget.Old'), finding('longMethod', 'Other.Big', 'BL\\Other.cs')]
REQUIRED = {'p::a': 'Passed', 'p::b': 'Passed'}
PASSING = {'p::a': 'Passed', 'p::b': 'Passed', 'p::c': 'Failed'}


class SelectionTests(unittest.TestCase):
    def test_findings_are_same_type_in_the_unit_file_only(self):
        self.assertEqual([f['symbolName'] for f in v05.file_findings(BEFORE, PATH)], ['Widget.Big', 'Widget.Old'])

    def test_folder_case_differences_between_git_and_the_working_copy_do_not_matter(self):
        self.assertTrue(v05.in_file(finding('longMethod', 'Widget.Big', 'bl\\widget.cs'), 'Ibis.Calculeren/BL/Widget.cs'))
        self.assertFalse(v05.in_file(finding('longMethod', 'Widget.Big', 'bl\\other.cs'), 'Ibis.Calculeren/BL/Widget.cs'))

    def test_unit_findings_are_the_audit_symbols_the_detector_reproduces(self):
        reproduced, missing = v05.unit_findings(BEFORE, ['Widget.Big', 'Widget.Gone'], PATH)
        self.assertEqual([f['symbolName'] for f in reproduced], ['Widget.Big'])
        self.assertEqual(missing, ['Widget.Gone'])

    def test_required_tests_are_those_passing_at_the_post_commit_state(self):
        self.assertEqual(v05.required_tests({'p::a': 'Passed', 'p::c': 'Failed'}), {'p::a': 'Passed'})


class VerdictTests(unittest.TestCase):
    def verdict(self, **overrides):
        args = dict(build_ok=True, api_missing=[], required=REQUIRED, outcomes=PASSING, unit_symbols=UNIT,
                    before=BEFORE, after=[finding('longMethod', 'Widget.Old')], path=PATH)
        args.update(overrides)
        return v05.verdict(**args)

    def test_success_needs_every_gate(self):
        v = self.verdict()
        self.assertTrue(v['success'])
        self.assertIsNone(v['stage'])

    def test_the_first_failed_gate_is_the_stage(self):
        self.assertEqual(self.verdict(build_ok=False)['stage'], 'build')
        self.assertEqual(self.verdict(api_missing=['W.M()'])['stage'], 'api')
        self.assertEqual(self.verdict(outcomes={'p::a': 'Passed', 'p::b': 'Failed'})['stage'], 'tests')
        self.assertEqual(self.verdict(after=BEFORE)['stage'], 'resolved')
        self.assertEqual(self.verdict(after=[finding('longMethod', 'Widget.Old'), finding('longMethod', 'Widget.New')])['stage'], 'no_new_debt')

    def test_a_missing_test_counts_as_failed(self):
        self.assertEqual(self.verdict(outcomes={'p::a': 'Passed'})['stage'], 'tests')

    def test_new_god_class_is_new_debt(self):
        self.assertEqual(self.verdict(after=[finding('godClass', 'N.Widget')])['stage'], 'no_new_debt')

    def test_without_an_oracle_the_tests_gate_is_not_applicable(self):
        v = self.verdict(required={}, outcomes={})
        self.assertTrue(v['success'])
        self.assertFalse(v['tests_applicable'])

    def test_success_without_the_new_debt_gate_is_reported(self):
        v = self.verdict(after=[finding('longMethod', 'Widget.Old'), finding('longMethod', 'Widget.New')])
        self.assertFalse(v['success'])
        self.assertTrue(v['success_without_new_debt'])

    def test_gates_after_the_failed_one_are_not_evaluated(self):
        v = self.verdict(build_ok=False, outcomes=None, after=None)
        self.assertEqual(v['gates'], dict(build=False, api=None, tests=None, resolved=None, no_new_debt=None))


class StubTests(unittest.TestCase):
    def test_truncation_drops_the_closing_line(self):
        self.assertEqual(v05.truncated('a\nb\n}\n'), 'a\nb')

    def test_stub_kinds(self):
        self.assertEqual(sorted(v05.STUBS), ['identity', 'revert', 'truncate'])


class OrderTests(unittest.TestCase):
    def test_unit_ids_follow_the_frame_order(self):
        self.assertEqual(v05.unit_id(0), 'U01')
        self.assertEqual(v05.unit_id(35), 'U36')

    def test_allocation_is_per_unit(self):
        self.assertEqual(v05.ALLOCATION, 120_000)


if __name__ == '__main__':
    unittest.main()
