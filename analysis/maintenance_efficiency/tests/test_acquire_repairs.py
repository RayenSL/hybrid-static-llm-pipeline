import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import acquire_repairs as acquire

FINDING = {'type': 'godClass', 'severity': 'critical', 'symbolName': 'N.BWidget', 'filePath': 'Core\\Widget.cs',
           'line': 12, 'snippet': 'class BWidget', 'metrics': {'ATFD': 9, 'WMC': 60, 'TCC': 0.1}}


class InputTests(unittest.TestCase):
    def test_finding_to_cli_input_line(self):
        line = json.loads(acquire.cli_input(FINDING, Path('C:/clone/Ibis.Calculeren')))
        self.assertEqual(line['anti_pattern_type'], 'GodClass')
        self.assertEqual(line['symbol_name'], 'N.BWidget')
        self.assertEqual(Path(line['file_path']), Path('C:/clone/Ibis.Calculeren/Core/Widget.cs'))
        self.assertEqual(line['line'], 12)
        self.assertEqual(line['metrics']['WMC'], 60)

    def test_long_method_type_name(self):
        self.assertEqual(json.loads(acquire.cli_input(dict(FINDING, type='longMethod'), Path('C:/x')))['anti_pattern_type'], 'LongMethod')


class AcceptanceTests(unittest.TestCase):
    def test_first_attempt_passing_every_gate_is_accepted(self):
        attempts = [dict(run=1, build=True, resolved=False, new_same_type=0, api_missing=[], tests_ok=True),
                    dict(run=2, build=True, resolved=True, new_same_type=0, api_missing=[], tests_ok=True),
                    dict(run=3, build=True, resolved=True, new_same_type=0, api_missing=[], tests_ok=True)]
        accepted, flow = acquire.accept(attempts)
        self.assertEqual(accepted, 2)
        self.assertEqual(flow, dict(attempted=3, built=3, resolved=2, no_new_same_type=2, api_preserved=2, tests_passed=2, accepted=1))

    def test_api_or_test_failure_rejects(self):
        attempts = [dict(run=1, build=True, resolved=True, new_same_type=0, api_missing=['A.M()'], tests_ok=True),
                    dict(run=2, build=True, resolved=True, new_same_type=1, api_missing=[], tests_ok=True),
                    dict(run=3, build=True, resolved=True, new_same_type=0, api_missing=[], tests_ok=False)]
        self.assertIsNone(acquire.accept(attempts)[0])


if __name__ == '__main__':
    unittest.main()
