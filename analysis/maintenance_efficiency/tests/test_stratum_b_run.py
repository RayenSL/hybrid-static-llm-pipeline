import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'reaccrual'))
import stratum_b_run as run

ORIGINAL = '''namespace Ordering;
public sealed class CheckoutCoordinator {
    private readonly IShipper _shipper;
    public string Checkout(Order order, Customer customer) => _shipper.Name;
}'''
SUPPORTING = {
    'IShipper.cs': 'namespace Ordering;\npublic interface IShipper { string Name { get; } }',
    'Order.cs': 'namespace Ordering;\npublic sealed class Order { public string Reference { get; set; } = ""; }',
    'Customer.cs': 'namespace Ordering;\npublic sealed class Customer { }\npublic enum CustomerTier { Standard }',
    'LabelPrinter.cs': 'namespace Ordering;\npublic sealed class LabelPrinter { }',
    'OrderShipperAdapter.cs': 'namespace Ordering;\ninternal sealed class OrderShipperAdapter { }',
}
BODIES = {
    1: 'Check("S1-a", true, () => true);\nCheck("S1-r", false, () => true);\n',
    2: 'Check("S2-a", true, () => true);\nCheck("S2-r", false, () => true);\n',
}


class ContextTests(unittest.TestCase):
    def test_closure_holds_files_declaring_types_the_original_references(self):
        self.assertEqual(run.closure_files(ORIGINAL, SUPPORTING), ['Customer.cs', 'IShipper.cs', 'Order.cs'])

    def test_a_type_name_inside_a_longer_identifier_does_not_count(self):
        self.assertNotIn('OrderShipperAdapter.cs', run.closure_files(ORIGINAL, SUPPORTING))

    def test_prompt_holds_requirement_context_and_numbered_editable_file(self):
        messages = run.render_prompt('Add a rule.', 'a\nb', 'src/Ordering/X.cs', {'Order.cs': 'class Order {}'})
        user = messages[1]['content']
        self.assertEqual(messages[0]['content'], run.SYSTEM)
        self.assertIn('Add a rule.', user)
        self.assertIn('Order.cs', user)
        self.assertIn('class Order {}', user)
        self.assertIn('1| a\n2| b', user)
        self.assertLess(user.index('Add a rule.'), user.index('1| a'))


class CaseTests(unittest.TestCase):
    def test_step_cases_are_fail_to_pass_and_earlier_cases_are_retained_unless_superseded(self):
        fail_to_pass, required = run.required_cases(BODIES, 2, {'S1-r'})
        self.assertEqual(fail_to_pass, ['S2-a'])
        self.assertEqual(required, {'S1-a', 'S2-a', 'S2-r'})

    def test_test_file_concatenates_bodies_up_to_the_step(self):
        text = run.test_file(BODIES, 1, 'HELPERS')
        self.assertIn('S1-a', text)
        self.assertNotIn('S2-a', text)
        self.assertTrue(text.endswith('HELPERS'))


class EditTests(unittest.TestCase):
    def test_line_edits_keep_their_coordinates_on_crlf_sources(self):
        previous = 'class A\r\n{\r\n    int x;\r\n}\r\n'
        response = '{"edits":[{"file":"src/A.cs","start_line":3,"end_line":3,"text":"    int y;"}]}'
        self.assertEqual(run.apply_edits(previous, 'src/A.cs', response), 'class A\r\n{\r\n    int y;\n}\r\n')

    def test_whole_file_replacement_of_a_crlf_source_leaves_nothing_behind(self):
        previous = 'a\r\nb\r\nc\r\n'
        response = run.rr.developer_stub_response(previous, 'x\r\ny\r\n', 'src/A.cs')
        self.assertEqual(run.apply_edits(previous, 'src/A.cs', response), 'x\r\ny\r\n')


class VerdictTests(unittest.TestCase):
    def test_tests_that_do_not_compile_fail_the_requirement_not_the_build(self):
        self.assertEqual(run.verdict(True, [], None, ['S1-a'], {'S1-a', 'S1-r'}, True), (False, 'fail_to_pass'))

    def test_order_build_api_fail_to_pass_regression(self):
        passed = {'S1-a': 'Passed', 'S1-r': 'Passed'}
        self.assertEqual(run.verdict(False, [], passed, ['S1-a'], set(passed), True), (False, 'build'))
        self.assertEqual(run.verdict(True, ['A.M()'], passed, ['S1-a'], set(passed), True), (False, 'api'))
        self.assertEqual(run.verdict(True, [], dict(passed, **{'S1-r': 'Failed'}), ['S1-a'], set(passed), True), (False, 'regression'))
        self.assertEqual(run.verdict(True, [], passed, ['S1-a'], set(passed), True), (True, None))


if __name__ == '__main__':
    unittest.main()
