import subprocess
import sys
import unittest

import analysis.context_ladder_industrial_analysis as industrial


class ContextLadderIndustrialAnalysisTests(unittest.TestCase):
    def test_script_entry_point_can_load_help(self):
        result = subprocess.run(
            [sys.executable, "analysis/context_ladder_industrial_analysis.py", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_target_id_for_maps_every_admitted_file_name(self):
        self.assertEqual("BES-LM-01", industrial.target_id_for(
            r"Z:\GitHub\Ibis.Besteksadministratie\Source\WebCore\Brink.GWW.Web.Core\Application\Extensions.cs"))
        self.assertEqual("BES-GC-01", industrial.target_id_for(
            r"Z:\GitHub\Ibis.Besteksadministratie\Source\WebCore\Brink.GWW.Web.Core\Reports\ReportHelpers.cs"))
        self.assertEqual("BES-LM-08", industrial.target_id_for(
            "Z:/GitHub/Ibis.Besteksadministratie/Source/.../ProjectManagerProject.cs"))

    def test_target_id_for_rejects_unmapped_file(self):
        with self.assertRaises(KeyError):
            industrial.target_id_for(r"Z:\Somewhere\Unrelated.cs")

    def test_metric_delta_is_missing_when_quality_row_is_absent(self):
        self.assertIsNone(industrial.metric_delta(None, "smell_total_before", "smell_total_after"))
        self.assertIsNone(industrial.metric_delta(
            {"smell_total_before": None, "smell_total_after": 5}, "smell_total_before", "smell_total_after"))

    def test_metric_delta_computes_after_minus_before(self):
        row = {"smell_total_before": 128, "smell_total_after": 122}
        self.assertEqual(-6, industrial.metric_delta(row, "smell_total_before", "smell_total_after"))

    def test_level_row_tallies_ordinal_ladder_and_oracle_outcomes(self):
        rows = [
            {"verified_repair_ladder": "resolved", "oracle_outcome": "behaviour_preserved",
             "quality_outcome": "scored", "smell_delta": -1, "ca_headline_delta": 0, "ca_all_delta": -2,
             "cross_file_declarations_n": 0, "cross_file_truncated": False,
             "input_tokens": 100, "output_tokens": 200, "cost_usd": 0.0065, "prompt_characters": 500},
            {"verified_repair_ladder": "build_fails", "oracle_outcome": "production_build_failed",
             "quality_outcome": "production_build_failed", "smell_delta": None, "ca_headline_delta": None,
             "ca_all_delta": None, "cross_file_declarations_n": 2, "cross_file_truncated": True,
             "input_tokens": 50, "output_tokens": 20, "cost_usd": 0.00085, "prompt_characters": 300},
        ]
        row = industrial.level_row("full", rows)
        self.assertEqual(2, row["n"])
        self.assertEqual(1, row["resolved"])
        self.assertEqual(1, row["build_fails"])
        self.assertEqual(1, row["oracle_behaviour_preserved"])
        self.assertEqual(1, row["oracle_production_build_failed"])
        self.assertEqual(1, row["quality_scored"])
        self.assertEqual(-1, row["smell_delta_mean"])
        self.assertEqual(1, row["cross_file_truncated_n"])
        self.assertEqual(50.0, row["truncation_rate_pct"])

    def test_target_row_flags_god_class_and_reader_rejected_targets(self):
        rows = [{"verified_repair_ladder": "resolved", "oracle_outcome": "behaviour_preserved",
                 "symbol_name": "Brink.GWW.Web.Reports.ReportHelpers", "anti_pattern_type": "god_class",
                 "context_level": "full", "cross_file_declarations_n": 0}]
        row = industrial.target_row("BES-GC-01", rows)
        self.assertTrue(row["is_god_class_n_of_1"])
        self.assertFalse(row["is_reader_rejected"])
        self.assertTrue(row["full_has_no_cross_file_payload"])


if __name__ == "__main__":
    unittest.main()
