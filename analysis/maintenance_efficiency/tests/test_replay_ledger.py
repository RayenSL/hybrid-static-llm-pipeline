import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import replay_ledger as ledger


def fresh(path, ceiling=1000, recorded=600):
    path.write_text(json.dumps(dict(authorised_ceiling=ceiling, cumulative_recorded_tokens=recorded, remaining=ceiling - recorded,
                                    available_unreserved=ceiling - recorded,
                                    entries=[dict(experiment='old', status='completed', recorded_tokens=recorded, reserved_tokens=0)])),
                    encoding='utf-8')


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = Path(self.dir) / 'ledger.json'
        fresh(self.path)

    def test_open_requires_reconciled_entries(self):
        ledger.open_entry(self.path, 'run1', 'out')
        with self.assertRaises(ValueError):
            ledger.open_entry(self.path, 'run2', 'out')

    def test_reserve_and_reconcile(self):
        ledger.open_entry(self.path, 'run1', 'out')
        ledger.reserve(self.path, 'run1', 300)
        state = json.loads(self.path.read_text())
        self.assertEqual(state['available_unreserved'], 100)
        ledger.reconcile(self.path, 'run1', reserved=300, used=120)
        state = json.loads(self.path.read_text())
        self.assertEqual(state['cumulative_recorded_tokens'], 720)
        self.assertEqual(state['remaining'], 280)
        self.assertEqual(state['available_unreserved'], 280)
        self.assertEqual(state['entries'][-1]['recorded_tokens'], 120)
        self.assertEqual(state['entries'][-1]['reserved_tokens'], 0)

    def test_reservation_beyond_ceiling_is_refused(self):
        ledger.open_entry(self.path, 'run1', 'out')
        with self.assertRaises(ValueError):
            ledger.reserve(self.path, 'run1', 401)

    def test_overrun_is_recorded_then_raised(self):
        ledger.open_entry(self.path, 'run1', 'out')
        ledger.reserve(self.path, 'run1', 100)
        with self.assertRaises(ValueError):
            ledger.reconcile(self.path, 'run1', reserved=100, used=150)
        self.assertEqual(json.loads(self.path.read_text())['cumulative_recorded_tokens'], 750)

    def test_close_marks_completed(self):
        ledger.open_entry(self.path, 'run1', 'out')
        ledger.close_entry(self.path, 'run1')
        self.assertEqual(json.loads(self.path.read_text())['entries'][-1]['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
