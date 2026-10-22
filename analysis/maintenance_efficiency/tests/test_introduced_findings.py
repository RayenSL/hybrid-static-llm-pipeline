import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import introduced_findings as intro

PATH = 'src/Ordering/OrderImporter.cs'


def finding(kind, symbol, path='src\\Ordering\\OrderImporter.cs'):
    return dict(type=kind, symbolName=symbol, filePath=path)


class IntroducedTests(unittest.TestCase):
    def test_new_findings_of_either_type_in_the_target_file_only(self):
        before = [finding('godClass', 'Ordering.OrderImporter')]
        after = before + [finding('longMethod', 'OrderImporter.Parse'), finding('longMethod', 'Other.Run', 'src\\Ordering\\Other.cs'),
                          finding('obsoleteApiUsage', 'X → Y')]
        self.assertEqual(intro.introduced(before, after, PATH), {('longMethod', 'OrderImporter.Parse')})

    def test_a_finding_present_at_step_0_is_not_introduced(self):
        before = [finding('longMethod', 'OrderImporter.Parse')]
        self.assertEqual(intro.introduced(before, before, PATH), set())

    def test_two_sided_sign_flip_is_symmetric(self):
        self.assertAlmostEqual(intro.two_sided([1.0, 2.0, 3.0]), intro.two_sided([-1.0, -2.0, -3.0]))
        self.assertEqual(intro.two_sided([0.0, 0.0]), 1.0)


if __name__ == '__main__':
    unittest.main()
