import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import replay_freeze as freeze

MANIFEST = dict(targets=[dict(steps=[dict(oracle_classes=[dict(step_id='T01S1')]), dict(oracle_classes=[dict(step_id='T01S1'), dict(step_id='T01S2')])])])
SETTINGS = dict(context_window_confirmed_tokens=128000, input_bound_tokens=49152, max_completion_tokens_per_call=4096,
                organisational_approval_recorded=True, required_ceiling_tokens=9_000_000)
LEDGER = dict(authorised_ceiling=9_500_000, entries=[dict(status='completed', reserved_tokens=0)])
DECISIONS = {'T01S1': dict(decision='accept'), 'T01S2': dict(decision='edit'), 'T05S2': dict(decision='reject')}


class GateTests(unittest.TestCase):
    def test_all_gates_met(self):
        self.assertEqual(freeze.gate_problems(MANIFEST, DECISIONS, SETTINGS, LEDGER), [])

    def test_pending_review_blocks(self):
        problems = freeze.gate_problems(MANIFEST, dict(DECISIONS, T01S2=dict(decision=None)), SETTINGS, LEDGER)
        self.assertIn('oracle review pending: T01S2', problems)

    def test_rejected_class_still_in_manifest_blocks(self):
        problems = freeze.gate_problems(MANIFEST, dict(DECISIONS, T01S1=dict(decision='reject')), SETTINGS, LEDGER)
        self.assertIn('manifest uses rejected oracle class T01S1; rebuild the manifest', problems)

    def test_context_window_must_cover_input_and_output(self):
        problems = freeze.gate_problems(MANIFEST, DECISIONS, dict(SETTINGS, context_window_confirmed_tokens=50000), LEDGER)
        self.assertTrue(any('context window' in p for p in problems))
        problems = freeze.gate_problems(MANIFEST, DECISIONS, dict(SETTINGS, context_window_confirmed_tokens=None), LEDGER)
        self.assertTrue(any('context window' in p for p in problems))

    def test_approval_and_ceiling(self):
        problems = freeze.gate_problems(MANIFEST, DECISIONS, dict(SETTINGS, organisational_approval_recorded=False),
                                        dict(LEDGER, authorised_ceiling=672000))
        self.assertIn('organisational approval for sending Bouw source not recorded', problems)
        self.assertTrue(any('ceiling' in p for p in problems))

    def test_unreconciled_ledger_blocks(self):
        problems = freeze.gate_problems(MANIFEST, DECISIONS, SETTINGS, dict(LEDGER, entries=[dict(status='running', reserved_tokens=0)]))
        self.assertIn('ledger has an unreconciled entry', problems)


class HashTests(unittest.TestCase):
    def test_changed_file_is_detected(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        f = d / 'a.txt'
        f.write_text('x', encoding='utf-8')
        record = freeze.hash_files([f])
        self.assertEqual(freeze.changed_files(record), [])
        f.write_text('y', encoding='utf-8')
        self.assertEqual(freeze.changed_files(record), [str(f)])


class RepairInputTests(unittest.TestCase):
    def test_accepted_repairs_and_the_acquisition_table_are_frozen(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        for tid in ('T01', 'T04', 'T07'):
            (d / tid).mkdir()
        (d / 'T01' / 'repaired.cs').write_text('a')
        (d / 'T07' / 'repaired.cs').write_text('b')
        (d / 'acquisition.json').write_text('[]')
        self.assertEqual(freeze.repair_inputs(d), [d / 'acquisition.json', d / 'T01' / 'repaired.cs', d / 'T07' / 'repaired.cs'])


if __name__ == '__main__':
    unittest.main()
