import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'detectors'))
from legacy_python import analyse
class LegacyTests(unittest.TestCase):
 def test_python2_exec_and_soft_async(self):
  ds,errors=analyse(b'def f(async=False):\n exec action.code in localdict\n if async: return 1\n return 0\n','example.py')
  self.assertEqual(errors,[]);self.assertEqual(ds[0]['metrics']['cyclomatic_complexity'],2)
 def test_nested_function_is_separate(self):
  ds,errors=analyse(b'def outer(x):\n def inner(y):\n  if y: return 1\n  return 0\n if x and x>1: return inner(x)\n return 0\n','example.py')
  self.assertEqual(errors,[]);self.assertEqual({x['symbol']:x['metrics']['cyclomatic_complexity'] for x in ds},{'outer':3,'outer.inner':2})
 def test_latin1_bytes_preserved(self):
  data=b'# coding: latin-1\ndef f():\n return "caf\xe9"\n';ds,errors=analyse(data,'example.py')
  self.assertEqual(errors,[]);span=ds[0]['span'];self.assertEqual(data[span['byte_start']:span['byte_end']],b'def f():\n return "caf\xe9"')
 def test_python3_print_and_soft_keyword_mode(self):
  ds,errors=analyse(b'def f(async=False):\n print("x", file=stream)\n return async\n','example.py',python3_mode=True)
  self.assertEqual(errors,[]);self.assertEqual(ds[0]['metrics']['cyclomatic_complexity'],1)
 def test_bare_and_typed_except_each_add_one(self):
  ds,errors=analyse(b'def f():\n try: pass\n except ValueError: pass\n except: pass\n','example.py')
  self.assertEqual(errors,[]);self.assertEqual(ds[0]['metrics']['cyclomatic_complexity'],3)
 def test_empty_except_is_rejected(self):
  ds,errors=analyse(b'def f():\n try: pass\n except Exception:\n if x: pass\n','example.py');self.assertTrue(errors)
if __name__=='__main__':unittest.main()
