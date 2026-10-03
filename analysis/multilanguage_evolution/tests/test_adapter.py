import copy,importlib,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'detectors'))
from syntax_probe import analyse
from tree_sitter import Language,Parser
class MappingTests(unittest.TestCase):
 def parse(self,lang,text):return analyse(text.encode(),'fixture',lang,Parser(Language(importlib.import_module('tree_sitter_'+lang).language())))
 def test_python_nested_function_not_charged_to_parent(self):
  ds,errors=self.parse('python','def outer(x):\n def inner(y):\n  if y: return 1\n  return 0\n if x and x > 1: return inner(x)\n return 0\n')
  self.assertEqual(errors,[]);self.assertEqual({d['symbol']:d['metrics']['cyclomatic_complexity'] for d in ds},{'outer':3,'outer.inner':2})
 def test_java_abstract_excluded_constructor_included(self):
  ds,errors=self.parse('java','abstract class A { abstract void empty(); A() {} int f(int x) { if (x>0 && x<3) return 1; return 0; } }')
  self.assertEqual(errors,[]);self.assertEqual([d['metrics']['cyclomatic_complexity'] for d in ds],[1,3])
 def test_c_short_circuit_loop(self):
  ds,errors=self.parse('c','int f(int x) { while (x && x>2) { x--; } return x; }')
  self.assertEqual(errors,[]);self.assertEqual(ds[0]['metrics']['cyclomatic_complexity'],3)
 def test_cpp_lambda_not_charged_to_parent(self):
  ds,errors=self.parse('cpp','int f(int x) { auto g=[](int y){ if(y) return 1; return 0; }; return g(x); }')
  self.assertEqual(errors,[]);self.assertEqual(ds[0]['metrics']['cyclomatic_complexity'],1)
 def test_invalid_source_reports_error(self):
  _,errors=self.parse('python','def broken(:\n return 1\n');self.assertTrue(errors)
if __name__=='__main__':unittest.main()
