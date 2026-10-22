import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import replay_ledger as ledger
import replay_run as run


class RecoverTests(unittest.TestCase):
    def test_running_entry_is_closed_and_charged_at_reservation(self):
        path = Path(tempfile.mkdtemp()) / 'ledger.json'
        path.write_text(json.dumps(dict(authorised_ceiling=1000, cumulative_recorded_tokens=100, remaining=900, available_unreserved=600,
                                        entries=[dict(experiment='old', status='running', recorded_tokens=100, reserved_tokens=300)])), encoding='utf-8')
        recovered = ledger.recover_interrupted(path, 'interrupted run')
        state = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(recovered, ['old'])
        self.assertEqual(state['entries'][0]['status'], 'completed')
        self.assertEqual(state['entries'][0]['reserved_tokens'], 0)
        self.assertEqual(state['cumulative_recorded_tokens'], 400)
        self.assertIn('interrupted run', state['entries'][0]['note'])

    def test_nothing_to_recover(self):
        path = Path(tempfile.mkdtemp()) / 'ledger.json'
        path.write_text(json.dumps(dict(authorised_ceiling=1000, cumulative_recorded_tokens=0, remaining=1000, available_unreserved=1000,
                                        entries=[dict(experiment='old', status='completed', recorded_tokens=0, reserved_tokens=0)])), encoding='utf-8')
        self.assertEqual(ledger.recover_interrupted(path, 'x'), [])


class ResumeTests(unittest.TestCase):
    def test_completed_targets_skipped_and_partial_ones_moved_aside(self):
        out = Path(tempfile.mkdtemp())
        (out / 'T01').mkdir()
        (out / 'T01' / 'complete.json').write_text('{}', encoding='utf-8')
        (out / 'T03' / 'O1' / 'S1').mkdir(parents=True)
        skip, moved = run.prepare_resume(out, ['T01', 'T03', 'T04'])
        self.assertEqual(skip, {'T01'})
        self.assertEqual(len(moved), 1)
        self.assertFalse((out / 'T03').exists())
        self.assertTrue(Path(moved[0]).exists())


class RepairStartTests(unittest.TestCase):
    def test_repaired_branch_starts_from_accepted_repair(self):
        repairs = Path(tempfile.mkdtemp())
        (repairs / 'T01').mkdir()
        (repairs / 'T01' / 'repaired.cs').write_bytes(b'class Repaired {}\n')
        states = run.initial_states([('O', 1), ('R', 1)], 'class Original {}\n', repairs, 'T01')
        self.assertEqual(states[('O', 1)], 'class Original {}\n')
        self.assertEqual(states[('R', 1)], 'class Repaired {}\n')

    def test_repaired_branch_dropped_without_accepted_repair(self):
        states = run.initial_states([('O', 1), ('R', 1)], 'class Original {}\n', Path(tempfile.mkdtemp()), 'T01')
        self.assertNotIn(('R', 1), states)


if __name__ == '__main__':
    unittest.main()
