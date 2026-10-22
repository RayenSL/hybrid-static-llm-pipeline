import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import introduction_audit as audit


def method(symbol, cc, lines=20, line=1):
    return dict(symbol=symbol, complexity=cc, lines=lines, line=line)


def klass(symbol, wmc, line=1):
    return dict(symbol=symbol, wmc=wmc, line=line)


class FileFilterTests(unittest.TestCase):
    def test_production_csharp_only(self):
        self.assertTrue(audit.is_production('Ibis.Calculeren/BL/Widget.cs'))
        self.assertFalse(audit.is_production('Ibis.Calculeren/BL.Tests/WidgetTests.cs'))
        self.assertFalse(audit.is_production('Ibis.Calculeren/UI/Main.Designer.cs'))
        self.assertFalse(audit.is_production('Ibis.Calculeren/Data/Model.g.cs'))
        self.assertFalse(audit.is_production('Ibis.Calculeren/BL/readme.md'))

    def test_name_status_parser_handles_renames(self):
        raw = b'M\x00a/B.cs\x00R087\x00a/Old.cs\x00a/New.cs\x00A\x00a/C.cs\x00D\x00a/D.cs\x00'
        self.assertEqual(audit.parse_name_status(raw), [('M', 'a/B.cs', 'a/B.cs'), ('R', 'a/Old.cs', 'a/New.cs'),
                                                       ('A', None, 'a/C.cs'), ('D', 'a/D.cs', None)])


class LongMethodTests(unittest.TestCase):
    def test_a_method_crossing_the_bound_is_an_introduction(self):
        found = audit.long_method_introductions([method('A.M', 10)], [method('A.M', 11)], gone_elsewhere=[])
        self.assertEqual([(f['symbol'], f['subtype'], f['kind']) for f in found], [('A.M', 'crossing', 'genuine')])

    def test_an_existing_long_method_that_grows_is_not_an_introduction(self):
        self.assertEqual(audit.long_method_introductions([method('A.M', 12)], [method('A.M', 20)], gone_elsewhere=[]), [])

    def test_a_new_long_method_is_an_introduction(self):
        found = audit.long_method_introductions([], [method('A.M', 13)], gone_elsewhere=[])
        self.assertEqual([(f['subtype'], f['kind']) for f in found], [('new_method', 'genuine')])

    def test_a_long_method_that_left_another_file_in_the_commit_is_a_relocation(self):
        found = audit.long_method_introductions([], [method('A.M', 13)], gone_elsewhere=[method('A.M', 13)])
        self.assertEqual(found[0]['kind'], 'relocation')

    def test_a_long_method_still_present_elsewhere_is_a_copy_not_a_relocation(self):
        self.assertEqual(audit.long_method_introductions([], [method('A.M', 13)], gone_elsewhere=[])[0]['kind'], 'genuine')

    def test_a_rename_in_the_same_file_with_the_same_complexity_and_size_is_a_rename(self):
        found = audit.long_method_introductions([method('A.Old', 15, lines=40)], [method('A.New', 15, lines=41)], gone_elsewhere=[])
        self.assertEqual(found[0]['kind'], 'rename')

    def test_a_move_with_a_rename_across_files_is_a_rename(self):
        found = audit.long_method_introductions([], [method('B.New', 15, lines=41)], gone_elsewhere=[method('A.Old', 15, lines=40)])
        self.assertEqual(found[0]['kind'], 'rename')

    def test_overloads_share_a_symbol_and_the_largest_counts(self):
        found = audit.long_method_introductions([method('A.M', 3), method('A.M', 4)], [method('A.M', 3), method('A.M', 12)], gone_elsewhere=[])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['complexity'], 12)

    def test_gone_methods_are_those_that_stopped_being_long(self):
        self.assertEqual([m['symbol'] for m in audit.gone_long_methods([method('A.M', 12), method('A.N', 12)], [method('A.M', 12), method('A.N', 5)])], ['A.N'])
        self.assertEqual([m['symbol'] for m in audit.gone_long_methods([method('A.M', 12)], [])], ['A.M'])


class OrdinaryCommitTests(unittest.TestCase):
    def test_commits_changing_at_most_the_bound_in_production_files(self):
        rows = [dict(production_files=['a'] * n) for n in (0, 1, 10, 11, 1000)]
        self.assertEqual([len(r['production_files']) for r in audit.ordinary(rows, 10)], [1, 10])


class GodClassCandidateTests(unittest.TestCase):
    def test_wmc_crossing_the_bound_is_a_candidate(self):
        found = audit.god_class_candidates([klass('N.C', 46)], [klass('N.C', 49)], gone_elsewhere=set())
        self.assertEqual([(f['symbol'], f['subtype']) for f in found], [('N.C', 'crossing')])

    def test_classes_already_over_the_bound_are_not_candidates(self):
        self.assertEqual(audit.god_class_candidates([klass('N.C', 50)], [klass('N.C', 55)], gone_elsewhere=set()), [])


class BandTests(unittest.TestCase):
    def test_complexity_bands(self):
        self.assertEqual([audit.band(c) for c in (11, 12, 14, 15, 19, 20, 60)], ['11', '12-14', '12-14', '15-19', '15-19', '20+', '20+'])


if __name__ == '__main__':
    unittest.main()
