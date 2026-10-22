import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import oracle_references as refs

SOURCE = '''namespace N;
public class Widget : Base { }
internal sealed class Helper<T> where T : class { }
public interface IThing { }
public enum Kind { A }
public record struct Point(int X);
// class Commented { }
'''


class ReferenceTests(unittest.TestCase):
    def test_declared_types(self):
        self.assertEqual(refs.declared_types(SOURCE), ['Widget', 'Helper', 'IThing', 'Kind', 'Point'])

    def test_test_paths_exclude_the_excluded_projects(self):
        self.assertTrue(refs.is_oracle_path('Ibis.Calculeren/BL.Tests/WidgetTests.cs'))
        self.assertTrue(refs.is_oracle_path('Ibis.Calculeren/BL.MsTests/WidgetTest.cs'))
        self.assertFalse(refs.is_oracle_path('Ibis.Calculeren/UI.Tests/DialogTests.cs'))
        self.assertFalse(refs.is_oracle_path('Ibis.Calculeren/IntegratieTests/Db.cs'))
        self.assertFalse(refs.is_oracle_path('Ibis.Calculeren/BL/Widget.cs'))

    def test_classification(self):
        self.assertEqual(refs.classify(['a/BL.Tests/X.cs']), 'direct')
        self.assertEqual(refs.classify([]), 'dependent_only')


if __name__ == '__main__':
    unittest.main()
