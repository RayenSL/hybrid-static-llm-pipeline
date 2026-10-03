import importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('python_semantic',HERE/'detectors/python/semantic.py');py=importlib.util.module_from_spec(spec);spec.loader.exec_module(py)
class PythonSemanticTests(unittest.TestCase):
    def test_deprecation_alias_dedup_and_shadowing(self):
        sources={'api.py':b'from typing_extensions import deprecated as dep\n@dep("use new")\ndef old(): pass\n','use.py':b'from api import old as alias\ndef caller():\n alias()\n alias()\ndef shadow(alias):\n alias()\n'}
        d=py.analyse(sources,{})
        self.assertEqual([(x['path'],x['symbol']) for x in d['obsolete']],[('use.py','api.old')])
        self.assertEqual(d['source_api_references'],1)
    def test_conditional_warning_does_not_deprecate_whole_api(self):
        sources={'a.py':b'import warnings\ndef old():\n warnings.warn("old", DeprecationWarning)\ndef conditional(x):\n if x: warnings.warn("argument", DeprecationWarning)\ndef caller():\n old()\n conditional(True)\n'}
        d=py.analyse(sources,{})
        self.assertEqual([x['symbol'] for x in d['obsolete']],['a.old'])
    def test_foreign_own_and_inherited_fields(self):
        source=b'class Data:\n a=1\n b=2\nclass Base:\n inherited=1\nclass Child(Base):\n def __init__(self): self.own=0\n def f(self, d: Data):\n  return d.a+d.a+d.b+self.own+self.inherited\n def g(self):\n  return self.own\n'
        d=py.analyse({'a.py':source},{('a.py',8):25,('a.py',10):25})
        c=next(c for c in d['classes'] if c['symbol']=='a.Child')
        self.assertEqual(c['atfd'],2);self.assertEqual(c['tcc'],1.0);self.assertEqual(c['unresolved_count'],0)
    def test_dynamic_receiver_is_unresolved(self):
        d=py.analyse({'a.py':b'class C:\n def f(self, unknown):\n  return unknown.field\n'},{('a.py',2):48})
        self.assertGreater(d['classes'][0]['unresolved_count'],0)
    def test_python2_syntax_uses_line_preserving_conversion(self):
        d=py.analyse({'a.py':b'# -*- coding: latin1 -*-\ndef f():\n \tprint "\xe9"\n'}, {})
        self.assertEqual(d['diagnostics'],[])
        self.assertEqual(d['parse_modes']['a.py'],'lib2to3-line-preserving')
    def test_python2_crlf_continued_raise_preserves_lines(self):
        source=b'def f():\r\n raise RuntimeError, \\\r\n  "old"\r\n'
        d=py.analyse({'a.py':source}, {})
        self.assertEqual((d['diagnostics'],d['parse_modes']['a.py']),([], 'lib2to3-line-preserving'))
class JavaSemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        cls.java=os.environ.get('EVOLUTION_TEST_JAVA');cls.classes=os.environ.get('EVOLUTION_TEST_JAVA_CLASSES')
        if not cls.java or not cls.classes:raise unittest.SkipTest('Set EVOLUTION_TEST_JAVA and EVOLUTION_TEST_JAVA_CLASSES for compiler integration tests')
    def scan(self,sources,release=None):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'source';root.mkdir()
            for name,text in sources.items():(root/name).write_text(text)
            out=Path(temp)/'result.json';subprocess.run([self.java,'-cp',self.classes,'SemanticScan',str(root),str(out),*(['',str(release)] if release else [])],check=True,capture_output=True)
            return json.loads(out.read_text())
    def test_composite_metrics_and_api_dedup(self):
        methods='\n'.join('public int m%d(Data d,int x){%s return d.a+d.b+d.c+d.d+d.e;}'%(i,'if(x>0)x--; '*7) for i in range(6))
        d=self.scan({'Data.java':'class Data { int a,b,c,d,e; }','God.java':'class God {'+methods+'}','Api.java':'class Api { @Deprecated static void old(){} }','Use.java':'class Use { void f(){Api.old();Api.old();} }'})
        self.assertEqual(d['semantic_errors'],0)
        c=next(x for x in d['classes'] if x['symbol']=='God')
        self.assertGreaterEqual(d['source_api_references'],1)
        self.assertEqual((c['wmc'],c['atfd'],c['tcc']),(48,5,0.0))
        self.assertEqual(len([x for x in d['obsolete'] if x['path']=='Use.java']),1)
    def test_inheritance_and_shared_field_cohesion(self):
        d=self.scan({'A.java':'class Base {int inherited;} class A extends Base {int own; public int f(){return own+inherited;} public int g(){return own;} }'})
        c=next(x for x in d['classes'] if x['symbol']=='A');self.assertEqual(c['atfd'],0);self.assertEqual(c['tcc'],1.0)
    def test_historical_underscore_uses_declared_release(self):
        source={'A.java':'class A { void f(){try {throw new Exception();} catch(Exception _) {}} }'}
        self.assertEqual(self.scan(source,8)['parse_errors'],0)
        self.assertGreater(self.scan(source,21)['parse_errors'],0)
    def test_unrelated_errors_do_not_invalidate_resolved_class(self):
        d=self.scan({'A.java':'class A {int x; public int f(){return x;} }','B.java':'class B {Missing missing;} '})
        self.assertGreater(d['semantic_errors'],0)
        self.assertEqual(next(c for c in d['classes'] if c['symbol']=='A')['unresolved_count'],0)
    def test_missing_dependency_reports_attribution_errors(self):
        d=self.scan({'A.java':'class A { Missing value; void f(){value.call();} }'});self.assertGreater(d['semantic_errors'],0)
if __name__=='__main__':unittest.main()
