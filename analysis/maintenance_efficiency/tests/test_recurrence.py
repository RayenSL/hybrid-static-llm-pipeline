import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import recurrence

PATH = 'Ibis.Calculeren/Core/Widget.cs'
FINDINGS = [
    {'type': 'godClass', 'symbolName': 'N.BWidget', 'filePath': 'Core\\Widget.cs'},
    {'type': 'longMethod', 'symbolName': 'N.BWidget.Compute', 'filePath': 'Core\\Widget.cs'},
    {'type': 'godClass', 'symbolName': 'N.Other', 'filePath': 'Core\\Other.cs'},
]


class RecurrenceTests(unittest.TestCase):
    def test_new_same_type_findings_in_target_file_only(self):
        self.assertEqual(recurrence.new_same_type(FINDINGS, PATH, 'godClass', set()), {'N.BWidget'})
        self.assertEqual(recurrence.new_same_type(FINDINGS, PATH, 'godClass', {'N.BWidget'}), set())

    def test_cross_type_findings_are_separate(self):
        self.assertEqual(recurrence.new_same_type(FINDINGS, PATH, 'longMethod', set()), {'N.BWidget.Compute'})

    def test_observation_first_recurrence(self):
        self.assertEqual(recurrence.observation([set(), {'X'}, {'X'}], completed=3), (2, True))

    def test_observation_censored_at_completed_steps(self):
        self.assertEqual(recurrence.observation([set(), set()], completed=2), (2, False))
        self.assertEqual(recurrence.observation([], completed=0), (0, False))


if __name__ == '__main__':
    unittest.main()
