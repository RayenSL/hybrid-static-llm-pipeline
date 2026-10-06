import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import shadow_frame as frame


def finding(symbol, cc, kind='genuine', subtype='crossing', file='ui/A.cs'):
    return dict(symbol=symbol, complexity=cc, lines=30, line=1, subtype=subtype, kind=kind, file=file)


class FrameTests(unittest.TestCase):
    def test_only_genuine_findings_are_candidates(self):
        record = dict(commit='c1', date='2020-01-01', long_method=[finding('A.M', 12), finding('A.N', 13, kind='relocation'), finding('A.O', 14, kind='rename')])
        self.assertEqual([c['symbol'] for c in frame.candidates([record], limit_tokens=None)], ['A.M'])

    def test_one_candidate_per_commit_the_most_complex_then_by_symbol(self):
        record = dict(commit='c1', date='2020-01-01', long_method=[finding('A.M', 12), finding('A.Z', 20), finding('A.B', 20)])
        self.assertEqual([c['symbol'] for c in frame.candidates([record], limit_tokens=None)], ['A.B'])

    def test_rank_is_a_seeded_hash_of_commit_and_symbol(self):
        self.assertEqual(frame.rank('s', 'c1', 'A.M'), frame.rank('s', 'c1', 'A.M'))
        self.assertNotEqual(frame.rank('s', 'c1', 'A.M'), frame.rank('s', 'c2', 'A.M'))

    def test_context_bound_uses_the_file_size_estimate(self):
        record = dict(commit='c1', date='2020-01-01', long_method=[finding('A.M', 12)])
        sizes = {('c1', 'ui/A.cs'): 32_000 * 3.5 + 10}
        self.assertEqual(frame.candidates([record], limit_tokens=32_000, sizes=sizes), [])
        sizes = {('c1', 'ui/A.cs'): 32_000 * 3.5 - 10}
        self.assertEqual(len(frame.candidates([record], limit_tokens=32_000, sizes=sizes)), 1)

    def test_strata_by_subtype_and_band(self):
        self.assertEqual(frame.stratum(finding('A.M', 11, subtype='crossing')), 'crossing|11')
        self.assertEqual(frame.stratum(finding('A.M', 25, subtype='new_method')), 'new_method|20+')

    def test_ordered_draw_takes_hash_order_within_each_stratum(self):
        rows = [dict(commit=f'c{i}', symbol='A.M', stratum='x' if i % 2 else 'y', complexity=12) for i in range(10)]
        order = frame.ordered(rows, 's')
        self.assertEqual(sorted(r['commit'] for r in order), sorted(r['commit'] for r in rows))
        hashes = [frame.rank('s', r['commit'], r['symbol']) for r in order if r['stratum'] == 'x']
        self.assertEqual(hashes, sorted(hashes))


if __name__ == '__main__':
    unittest.main()
