import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).parents[1]))
from accounting import summarize_run,price_call,campaign_efficiency,break_even


def call(**kw):return dict(dict(call_id='c1',model='test-model',outcome='completed',input_tokens=100,output_tokens=20,cached_input_tokens=40,reasoning_output_tokens=5),**kw)
def run(calls=None,**kw):return dict(dict(token_budget=200,calls=[call()] if calls is None else calls,acceptance_passed=True,regression_passed=True,edit_scope_passed=True,integrity_passed=True),**kw)
PRICES=dict(model='test-model',input_per_million='2',cached_input_per_million='0.5',output_per_million='10')

class AccountingTests(unittest.TestCase):
    def test_subsets_not_double_counted(self):
        r=summarize_run(run(),PRICES)
        self.assertEqual(r['total_tokens'],120)
        self.assertEqual(float(r['cost']),0.00034)
    def test_failed_call_usage_is_charged(self):
        r=summarize_run(run([call(outcome='failed'),call(call_id='c2')],token_budget=300))
        self.assertEqual(r['total_tokens'],240);self.assertEqual(r['failed_calls'],1)
    def test_unknown_usage_is_not_zero(self):
        r=summarize_run(run([call(input_tokens=None,cached_input_tokens=None)]))
        self.assertIsNone(r['total_tokens']);self.assertEqual(r['observed_token_lower_bound'],20)
        self.assertIsNone(r['correct_within_budget'])
    def test_budget_overshoot_fails_even_if_tests_pass(self):
        self.assertFalse(summarize_run(run(token_budget=119))['correct_within_budget'])
        self.assertTrue(summarize_run(run(token_budget=120))['correct_within_budget'])
    def test_unknown_test_result_is_not_success(self):
        self.assertIsNone(summarize_run(run(acceptance_passed=None))['correct_within_budget'])
    def test_unverified_scope_and_integrity_never_count_as_success(self):
        self.assertIsNone(summarize_run(run(edit_scope_passed=None))["correct_within_budget"])
        self.assertFalse(summarize_run(run(integrity_passed=False))["correct_within_budget"])
    def test_missing_cache_split_does_not_invent_price(self):
        self.assertIsNone(price_call(call(cached_input_tokens=None),PRICES))
        self.assertIsNotNone(price_call(call(cached_input_tokens=None),{**PRICES,'cached_input_per_million':'2'}))
    def test_wrong_model_and_invalid_subsets_rejected(self):
        for c in [call(model='different'),call(cached_input_tokens=101),call(reasoning_output_tokens=21),call(input_tokens=-1),call(input_tokens=True)]:
            with self.assertRaises(ValueError):price_call(c,PRICES)
    def test_duplicate_calls_rejected(self):
        with self.assertRaises(ValueError):summarize_run(run([call(),call()]))
    def test_failed_runs_retained_in_efficiency(self):
        r=campaign_efficiency([run(),run(acceptance_passed=False)])
        self.assertEqual(r['tokens_per_success'],240);self.assertEqual(r['success_fraction_bounds'],[0.5,0.5])
    def test_zero_successes_have_no_finite_efficiency(self):
        self.assertIsNone(campaign_efficiency([run(acceptance_passed=False)])['tokens_per_success'])
    def test_unknown_outcomes_produce_bounds(self):
        r=campaign_efficiency([run(),run(acceptance_passed=None)])
        self.assertEqual(r['success_fraction_bounds'],[0.5,1]);self.assertIsNone(r['tokens_per_success'])
    def test_break_even_and_no_savings(self):
        self.assertEqual(break_even(30001,3000),11)
        self.assertIsNone(break_even(100,0));self.assertIsNone(break_even(100,-10))

if __name__=='__main__':unittest.main()
