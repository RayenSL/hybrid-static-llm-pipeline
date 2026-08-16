import unittest
import subprocess
import sys

import pandas as pd

import analysis.context_ladder_analysis as ladder


class ContextLadderAnalysisTests(unittest.TestCase):
    def test_script_entry_point_can_load_help(self):
        result = subprocess.run(
            [sys.executable, "analysis/context_ladder_analysis.py", "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_validator_accepts_twelve_attempts_per_instance(self):
        data = pd.DataFrame({
            "instance_id": [f"target-{i}" for i in range(36) for _ in range(12)],
            "context_level": [level for _ in range(36) for level in ladder.LEVELS for _ in range(3)],
        })

        self.assertEqual((432, 36), ladder.validate_model_ready_data(data))

    def test_validator_rejects_factorial_twenty_four_attempt_shape(self):
        data = pd.DataFrame({
            "instance_id": ["a"] * 24 + ["b"] * 24,
            "context_level": ["minimal"] * 48,
        })

        with self.assertRaisesRegex(ValueError, "12 context-ladder attempts"):
            ladder.validate_model_ready_data(data)

    def test_grade_obsolete_resolution_distinguishes_migration_and_evasion(self):
        self.assertEqual(
            "migrated",
            ladder.grade_obsolete_resolution("return MailApiV2.Send(message);", "MailApiV1"),
        )
        self.assertEqual(
            "evaded",
            ladder.grade_obsolete_resolution("Func<string,bool> f = MailApiV1.Send;", "MailApiV1"),
        )
        self.assertEqual(
            "ambiguous",
            ladder.grade_obsolete_resolution("return provider.Deliver(body);", "MailApiV1"),
        )
        self.assertEqual(
            "migrated",
            ladder.grade_obsolete_resolution("var writer = new SimpleDocumentWriter();", "RenderApiV1"),
        )
        self.assertEqual(
            "evaded",
            ladder.grade_obsolete_resolution("return countedQuantity - item.OnHand;", "SyncApiV1"),
        )

    def test_metric_delta_is_missing_for_unscored_quality_outcome(self):
        self.assertIsNone(ladder.metric_delta({"before": None, "after": None}, "before", "after"))

    def test_successor_subset_reports_detector_and_migration_counts(self):
        rows = [
            {"target": "EmailClient", "context_level": "full", "verified": 1, "obsolete_grade": "migrated"},
            {"target": "EmailClient", "context_level": "relational", "verified": 1, "obsolete_grade": "evaded"},
            {"target": "CalendarFeed", "context_level": "full", "verified": 1, "obsolete_grade": "migrated"},
        ]
        self.assertEqual(
            [{"level": "relational", "resolved": 1, "migrated": 0, "n": 1},
             {"level": "full", "resolved": 1, "migrated": 1, "n": 1}],
            ladder.successor_subset(rows),
        )

    def test_behavior_preserving_requires_both_detector_and_layer3(self):
        rows = [
            {"verified": 1, "layer3_passed": True},
            {"verified": 0, "layer3_passed": True},
            {"verified": 1, "layer3_passed": False},
        ]
        self.assertEqual(1, ladder.behavior_preserving_count(rows))


if __name__ == "__main__":
    unittest.main()
