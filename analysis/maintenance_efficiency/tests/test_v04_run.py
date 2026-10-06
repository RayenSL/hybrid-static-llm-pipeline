import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import v04_run as v04
import stratum_b_run as b

PATH = 'src/Ordering/OrderImporter.cs'
FINDING = dict(type='longMethod', symbolName='OrderImporter.Parse', filePath='src\\Ordering\\OrderImporter.cs', line=12,
               metrics=dict(CyclomaticComplexity=13, MaxCyclomaticComplexity=10))


class ArmTests(unittest.TestCase):
    def test_arms_start_from_original_or_repair(self):
        self.assertEqual({a: v04.ARMS[a]['start'] for a in v04.ARMS}, {'O-N': 'original', 'R-N': 'repair', 'R-D': 'repair', 'R-L': 'repair'})
        self.assertEqual([a for a in v04.ARMS if v04.ARMS[a]['loop']], ['R-L'])

    def test_design_guidance_extends_the_neutral_instruction_only_in_r_d(self):
        self.assertEqual(v04.system_for('R-N'), b.SYSTEM)
        self.assertEqual(v04.system_for('R-L'), b.SYSTEM)
        self.assertTrue(v04.system_for('R-D').startswith(b.SYSTEM))
        self.assertIn('keep methods short and focused', v04.system_for('R-D'))

    def test_arm_order_is_a_seeded_permutation(self):
        order = v04.arm_order('GC-02')
        self.assertEqual(sorted(order), sorted(v04.ARMS))
        self.assertEqual(order, v04.arm_order('GC-02'))

    def test_prompt_uses_the_arm_instruction(self):
        messages = b.render_prompt('Add a rule.', 'a', PATH, {}, system=v04.system_for('R-D'))
        self.assertEqual(messages[0]['content'], v04.system_for('R-D'))


class LoopTests(unittest.TestCase):
    def test_trigger_on_findings_absent_from_the_previous_state(self):
        self.assertEqual(v04.new_findings([], [FINDING], PATH), [FINDING])
        self.assertEqual(v04.new_findings([FINDING], [FINDING], PATH), [])

    def test_quality_prompt_reports_findings_and_never_tests(self):
        messages = v04.quality_prompt('Add a rule.', 'x\ny', PATH, {'Order.cs': 'class Order {}'}, [FINDING])
        user = messages[1]['content']
        self.assertEqual(messages[0]['content'], b.SYSTEM)
        self.assertIn('OrderImporter.Parse', user)
        self.assertIn('CyclomaticComplexity=13', user)
        self.assertIn('Restructure the editable file to remove them', user)
        self.assertIn('1| x\n2| y', user)
        self.assertNotIn('Check(', user)

    def test_restructuring_is_kept_only_when_it_passes_every_gate(self):
        self.assertEqual(v04.choose('candidate', 'restructured', dict(completed=True)), ('restructured', True))
        self.assertEqual(v04.choose('candidate', 'restructured', dict(completed=False, stage='regression')), ('candidate', False))
        self.assertEqual(v04.choose('candidate', None, None), ('candidate', False))


if __name__ == '__main__':
    unittest.main()
