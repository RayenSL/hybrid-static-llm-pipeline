import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
sys.path.insert(0, str(Path(__file__).parents[1] / 'natural_validation'))
import replay_run as run
import patches

STEP = dict(step=1, commit='abc', message='Fix rounding of totals\n\nWork item 123', other_files=['A/Caller.cs'])


class PromptTests(unittest.TestCase):
    def test_number_lines_is_one_based(self):
        self.assertEqual(run.number_lines('a\nb\n'), '1| a\n2| b')

    def test_prompt_contains_requirement_diff_and_numbered_file(self):
        messages = run.render_prompt(STEP, 'class C {}\n', 'Lib/C.cs', 'diff --git a/A/Caller.cs b/A/Caller.cs\n+x')
        user = messages[1]['content']
        self.assertIn('Fix rounding of totals', user)
        self.assertIn('diff --git a/A/Caller.cs', user)
        self.assertIn('1| class C {}', user)
        self.assertIn('"Lib/C.cs"', user)

    def test_required_signatures_are_listed_when_present(self):
        step = dict(STEP, api_signatures=['Calc: public int Mul(int a, int b);', 'Pair: public sealed class Pair : Calc'])
        user = run.render_prompt(step, 'class C {}\n', 'Lib/C.cs', '')[1]['content']
        self.assertIn('- Calc: public int Mul(int a, int b);', user)
        self.assertIn('- Pair: public sealed class Pair : Calc', user)
        self.assertNotIn('signatures', run.render_prompt(STEP, 'class C {}\n', 'Lib/C.cs', '')[1]['content'].lower())

    def test_prompt_is_neutral_about_design_and_branch(self):
        text = json.dumps(run.render_prompt(STEP, 'class C {}\n', 'Lib/C.cs', '')).lower()
        for word in ['refactor', 'repair', 'anti-pattern', 'god class', 'long method', 'structural', 'design', 'branch', 'original']:
            self.assertNotIn(word, text)


class StubProviderTests(unittest.TestCase):
    def test_developer_stub_returns_whole_file_patch_that_applies(self):
        current, developer = 'class C {\n int A;\n}\n', 'class C {\n int A;\n int B;\n}\n'
        content = run.developer_stub_response(current, developer, 'Lib/C.cs')
        tmp = Path(self._tmp()) / 'Lib'
        tmp.mkdir(parents=True)
        (tmp / 'C.cs').write_text(current, encoding='utf-8')
        patches.apply(tmp.parent, patches.parse(content), ['Lib/C.cs'])
        self.assertEqual((tmp / 'C.cs').read_text(encoding='utf-8'), developer)

    def test_noop_stub_is_a_valid_patch_that_changes_nothing(self):
        current = 'class C {\n int A;\n}\n'
        tmp = Path(self._tmp()) / 'Lib'
        tmp.mkdir(parents=True)
        (tmp / 'C.cs').write_text(current, encoding='utf-8')
        patches.apply(tmp.parent, patches.parse(run.noop_stub_response(current, 'Lib/C.cs')), ['Lib/C.cs'])
        self.assertEqual((tmp / 'C.cs').read_text(encoding='utf-8'), current)

    def _tmp(self):
        import tempfile
        d = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__('shutil').rmtree(d, ignore_errors=True))
        return d


if __name__ == '__main__':
    unittest.main()
