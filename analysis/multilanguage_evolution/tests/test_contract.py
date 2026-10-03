import copy,io,json,sys,tarfile,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'detectors'),str(ROOT/'ingest')]
from syntax_probe import run
from validate import validate
class ContractTests(unittest.TestCase):
 def result(self,source):
  with tempfile.TemporaryDirectory() as work:
   archive=Path(work)/'source.tar'
   with tarfile.open(archive,'w') as t:
    b=source.encode();m=tarfile.TarInfo('src/example.py');m.size=len(b);t.addfile(m,io.BytesIO(b))
   return run(archive,'python','https://example.invalid/repo','a'*40,{})
 def test_complete_zero_is_zero(self):
  d=self.result('def f():\n return 1\n');self.assertEqual(d['summary']['prevalence'],0);validate(d)
 def test_incomplete_is_null(self):
  d=self.result('def f(:\n return 1\n');self.assertIsNone(d['summary']['prevalence']);validate(d)
 def test_corrupt_denominator_rejected(self):
  d=self.result('def f():\n return 1\n');d['summary']['definition_count']=2
  with self.assertRaises(ValueError):validate(d)
 def test_probe_cannot_claim_scientific_admission(self):
  d=self.result('def f():\n return 1\n');d['admitted']=True
  with self.assertRaises(Exception):validate(d)
 def test_source_path_cannot_escape(self):
  d=self.result('def f():\n return 1\n');d['excluded']=[{'path':'../escape.py','reason':'test'}]
  with self.assertRaises(ValueError):validate(d)
 def test_no_physical_root_in_identity(self):
  a=self.result('def f():\n return 1\n');b=self.result('def f():\n return 1\n');self.assertEqual(a,b)
if __name__=='__main__':unittest.main()
