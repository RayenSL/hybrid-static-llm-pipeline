import copy,hashlib,json,sys,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE/'detectors'));sys.path.insert(0,str(HERE/'ingest'))
from multi_rule import canonical,finish
from validate_multi_rule import validate
class MultiRuleContractTests(unittest.TestCase):
    def fixture(self):
        return {'schema_version':'evolution.multi-rule/0.2','admitted':False,'repository':'https://example.org/repo','commit':'a'*40,'language':'python','archive_sha256':'b'*64,'scope':{},'scope_sha256':hashlib.sha256(canonical({})).hexdigest(),'syntax_report_sha256':'c'*64,'adapter_sha256':'d'*64,'tool':{'engine':'test'},'inventory':[],'rules':[finish('LongMethod','definitions',0,0,[],[]),finish('GodClass','classes',None,0,[],['No semantic coverage']),finish('ObsoleteApiUsage','file/API pairs',None,0,[],['No dependency catalogue'])],'class_metrics':[],'semantic_diagnostics':[],'semantic_coverage':{},'limitations':['fixture']}
    def test_complete_zero_and_unavailable_null_differ(self):
        d=self.fixture();validate(d);self.assertEqual(d['rules'][0]['finding_count'],0);self.assertIsNone(d['rules'][1]['finding_count'])
    def test_partial_zero_rejected(self):
        d=self.fixture();d['rules'][1]['finding_count']=0
        with self.assertRaises(Exception):validate(d)
    def test_missing_rule_rejected(self):
        d=self.fixture();d['rules'].pop()
        with self.assertRaises(Exception):validate(d)
    def test_duplicate_rule_rejected(self):
        d=self.fixture();d['rules'][2]=copy.deepcopy(d['rules'][1])
        with self.assertRaises(ValueError):validate(d)
    def test_admission_cannot_be_toggled(self):
        d=self.fixture();d['admitted']=True
        with self.assertRaises(Exception):validate(d)
    def test_scope_tampering_rejected(self):
        d=self.fixture();d['scope']['exclude']=['production/']
        with self.assertRaises(ValueError):validate(d)
if __name__=='__main__':unittest.main()
