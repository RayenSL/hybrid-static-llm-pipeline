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


class RootSolutionTests(unittest.TestCase):
    SLN = ('Microsoft Visual Studio Solution File, Format Version 12.00\n'
           'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "Lib", "Lib\\Lib.csproj", "{11111111-1111-1111-1111-111111111111}"\n'
           'EndProject\n'
           'Project("{2150E333-8FDC-42A3-9474-1A3956D46DE8}") = "Tests", "Tests", "{22222222-2222-2222-2222-222222222222}"\n'
           'EndProject\n'
           'Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "App", "App\\App.csproj", "{33333333-3333-3333-3333-333333333333}"\n'
           'EndProject\n')

    def test_project_paths_are_prefixed_with_the_solution_folder(self):
        text = acquire.root_solution_text(self.SLN, 'Ibis.Calculeren')
        self.assertIn('"Ibis.Calculeren\\Lib\\Lib.csproj"', text)
        self.assertIn('"Ibis.Calculeren\\App\\App.csproj"', text)

    def test_solution_folders_are_unchanged(self):
        self.assertIn('= "Tests", "Tests",', acquire.root_solution_text(self.SLN, 'Ibis.Calculeren'))


class NugetConfigTests(unittest.TestCase):
    def test_local_package_cache_is_a_source_and_the_licensed_feed_is_disabled(self):
        import xml.etree.ElementTree as ET
        root = ET.fromstring(acquire.nuget_config_text(Path('C:/Users/u/.nuget/packages')))
        self.assertEqual([e.get('value') for e in root.find('packageSources')], [str(Path('C:/Users/u/.nuget/packages'))])
        self.assertEqual([(e.get('key'), e.get('value')) for e in root.find('disabledPackageSources')], [('Infragistics', 'true')])


class ResolutionTests(unittest.TestCase):
    TARGET = dict(symbol='Widget.ReadXmlCompact', type='longMethod', path='Ibis.Calculeren/BL/Widget.cs')

    def finding(self, symbol, type_='longMethod', path='BL\\Widget.cs'):
        return dict(symbolName=symbol, type=type_, filePath=path)

    def test_an_overlapping_name_elsewhere_in_the_file_does_not_count_as_the_target(self):
        after = [self.finding('WidgetXml.ReadXml')]
        self.assertTrue(acquire.target_resolved(after, self.TARGET))

    def test_target_still_reported_is_unresolved(self):
        self.assertFalse(acquire.target_resolved([self.finding('Widget.ReadXmlCompact')], self.TARGET))

    def test_same_symbol_in_another_file_or_of_another_type_is_ignored(self):
        after = [self.finding('Widget.ReadXmlCompact', path='BL\\Other.cs'),
                 self.finding('Widget.ReadXmlCompact', type_='godClass')]
        self.assertTrue(acquire.target_resolved(after, self.TARGET))


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
