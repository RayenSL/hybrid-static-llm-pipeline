import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import v05_analyze as an


def unit(uid, file, **extra):
    return dict(unit_id=uid, file=file, commit=uid, symbols=['A.M'], **extra)


class FootprintTests(unittest.TestCase):
    def test_added_and_removed_lines(self):
        self.assertEqual(an.edit_footprint('a\nb\nc', 'a\nB\nc\nd'), dict(added=2, removed=1))

    def test_identical_files_have_no_footprint(self):
        self.assertEqual(an.edit_footprint('a\nb', 'a\nb'), dict(added=0, removed=0))


class ClusterTests(unittest.TestCase):
    def test_one_unit_per_file_without_regard_to_case_and_in_hash_order(self):
        units = [unit('U1', 'x/A.cs'), unit('U2', 'X/a.cs'), unit('U3', 'x/B.cs')]
        chosen = an.first_per_file(units, 's')
        self.assertEqual(len(chosen), 2)
        self.assertEqual(sorted(u['file'].lower() for u in chosen), ['x/a.cs', 'x/b.cs'])
        same_file = [u for u in units if u['file'].lower() == 'x/a.cs']
        expected = min(same_file, key=lambda u: an.rank('s', u['commit'], u['symbols'][0]))
        self.assertIn(expected, chosen)

    def test_clustered_bootstrap_resamples_files(self):
        lo, hi = an.clustered_interval({'f1': [1, 1], 'f2': [1], 'f3': [0]}, reps=500, seed=1)
        self.assertLess(lo, hi)
        self.assertEqual(an.clustered_interval({'f1': [1], 'f2': [1]}, reps=100, seed=1), (1.0, 1.0))


class ProfileTests(unittest.TestCase):
    def test_complexity_profile_of_the_unit_symbols_and_new_methods(self):
        before = [dict(symbol='A.M', complexity=12, lines=30, line=1)]
        after = [dict(symbol='A.M', complexity=7, lines=20, line=1), dict(symbol='A.M2', complexity=6, lines=12, line=30),
                 dict(symbol='A.M3', complexity=10, lines=12, line=50)]
        profile = an.complexity_profile(before, after, ['A.M'])
        self.assertEqual(profile['before'], {'A.M': 12})
        self.assertEqual(profile['after'], {'A.M': 7})
        self.assertEqual(profile['new_methods'], 2)
        self.assertEqual(profile['new_max_complexity'], 10)

    def test_near_threshold_counts_methods_just_under_the_bound(self):
        methods = [dict(symbol='A.a', complexity=c, lines=1, line=1) for c in (7, 8, 9, 10, 11)]
        self.assertEqual(an.near_threshold(methods), 3)


if __name__ == '__main__':
    unittest.main()
