import tempfile
import unittest
from pathlib import Path
from patches import apply, parse

class PatchContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'a.cs').write_bytes(b'one\ntwo\nthree\n')
    def tearDown(self):self.temp.cleanup()
    def patch(self,start,end,text='changed'):
        return {'edits':[dict(file='a.cs',start_line=start,end_line=end,text=text)]}
    def test_multiple_edits_use_original_coordinates(self):
        patch=self.patch(1,1,'first');patch['edits']+=self.patch(3,3,'last')['edits'];apply(self.root,patch,['a.cs'])
        self.assertEqual((self.root/'a.cs').read_text(),'first\ntwo\nlast\n')
    def test_insert_does_not_delete_original_line(self):
        apply(self.root,self.patch(2,1,'inserted'),['a.cs']);self.assertEqual((self.root/'a.cs').read_text(),'one\ninserted\ntwo\nthree\n')
    def test_overlapping_edits_rejected(self):
        patch=self.patch(1,2);patch['edits']+=self.patch(2,3)['edits']
        with self.assertRaises(ValueError):apply(self.root,patch,['a.cs'])
    def test_out_of_scope_rejected(self):
        patch=self.patch(1,1);patch['edits'][0]['file']='../a.cs'
        with self.assertRaises(ValueError):apply(self.root,patch,['a.cs'])
    def test_new_runtime_capability_rejected(self):
        with self.assertRaises(ValueError):apply(self.root,self.patch(1,1,'System.IO.File.ReadAllText("secret");'),['a.cs'])
    def test_boolean_and_out_of_bounds_coordinates_rejected(self):
        for start,end in [(True,1),(1,99)]:
            with self.assertRaises(ValueError):apply(self.root,self.patch(start,end),['a.cs'])
    def test_wrapper_and_unknown_schema_rejected(self):
        with self.assertRaises(ValueError):parse('{"edits":[],"execute":"x"}')
        with self.assertRaises(ValueError):parse('explanation {"edits":[]}')

if __name__=='__main__':unittest.main()
