import csv
import json
from pathlib import Path
import tempfile
import unittest

from analysis.thesis import tables


class ThesisTableTests(unittest.TestCase):
    def test_factorial_tables_match_final_pdf_denominators_and_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)
            tables.factorial_tables(tables.ROOT/'experiments/confirmatory-v2-gpt56-sol-20260812',out)
            with (out/'table_5_4_factorial_outcomes.csv').open() as handle:rows=list(csv.DictReader(handle))
            self.assertEqual(8,len(rows))
            self.assertEqual({78},{int(r['assignments']) for r in rows})
            self.assertEqual(586,sum(int(r['strict_success']) for r in rows))
            self.assertEqual(612,sum(int(r['private_pass']) for r in rows))
            with (out/'table_5_5_whole_solution_quality.csv').open() as handle:quality=list(csv.DictReader(handle))
            self.assertEqual([587,16,98],[int(r['decreased']) for r in quality])
            self.assertEqual({623},{int(r['states']) for r in quality})

    def test_maintenance_outputs_keep_model_populations_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)
            tables.maintenance_tables(tables.DATA/'maintenance_aggregates.json',out)
            with (out/'table_5_12_maintenance_outcomes.csv').open() as handle:rows=list(csv.DictReader(handle))
            self.assertEqual(8,len(rows))
            self.assertEqual({21},{int(r['targets']) for r in rows})
            self.assertEqual({84},{int(r['assigned_steps']) for r in rows})
            loops=[r for r in rows if r['arm']=='R-L']
            self.assertEqual([0,3],[int(r['affected_targets']) for r in loops])
            self.assertEqual([82,84],[int(r['completed_steps']) for r in loops])

    def test_retained_qualitative_sources_match_recorded_hashes(self):
        import hashlib
        evidence=tables.read(tables.DATA/'qualitative/evidence.json')
        for name, record in evidence['source_provenance'].items():
            content=(tables.DATA/'qualitative/sources'/name).read_bytes()
            self.assertEqual(record['copied_content_sha256'],hashlib.sha256(content).hexdigest(),name)


if __name__=='__main__':unittest.main()
