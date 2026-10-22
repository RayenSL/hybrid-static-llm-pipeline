import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import stratum_b_analyze as analyze

FINDINGS = [dict(type='longMethod', symbolName='OrderImporter.ImportBatch', filePath='src\\Ordering\\OrderImporter.cs'),
            dict(type='longMethod', symbolName='OrderImporter.Parse', filePath='src\\Ordering\\OrderImporter.cs'),
            dict(type='godClass', symbolName='Ordering.OrderImporter', filePath='src\\Ordering\\OrderImporter.cs'),
            dict(type='longMethod', symbolName='Other.Run', filePath='src\\Ordering\\Other.cs')]


class TargetTests(unittest.TestCase):
    def test_anti_pattern_type_from_target_id(self):
        self.assertEqual(analyze.target_type('GC-02'), 'godClass')
        self.assertEqual(analyze.target_type('LM-13'), 'longMethod')

    def test_symbols_of_one_type_in_the_target_file(self):
        self.assertEqual(analyze.symbols(FINDINGS, 'src/Ordering/OrderImporter.cs', 'longMethod'),
                         {'OrderImporter.ImportBatch', 'OrderImporter.Parse'})
        self.assertEqual(analyze.symbols(FINDINGS, 'src/Ordering/OrderImporter.cs', 'godClass'), {'Ordering.OrderImporter'})


if __name__ == '__main__':
    unittest.main()
