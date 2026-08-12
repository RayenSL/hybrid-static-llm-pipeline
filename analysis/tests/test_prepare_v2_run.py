import json
import tempfile
import unittest
from pathlib import Path

from analysis.prepare_v2_run import assess_readiness, build_run_spec


class PrepareV2RunTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.corpus = self.root / "corpus"
        self.pipeline = self.root / "pipeline"
        (self.corpus / "ground-truth" / "records").mkdir(parents=True)
        (self.pipeline / "layer3" / "golden").mkdir(parents=True)

        targets = []
        for prefix, anti_pattern in (("GC", "GodClass"), ("LM", "LongMethod")):
            for number in range(1, 14):
                instance_id = f"{prefix}-{number:02d}"
                source = self.corpus / "corpus" / "src" / instance_id / "Target.cs"
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text("public class Target {}\n", encoding="utf-8")
                record = {
                    "instance_id": instance_id,
                    "anti_pattern": anti_pattern,
                    "location": {
                        "file": f"src/{instance_id}/Target.cs",
                        "symbol": f"{instance_id}.Target",
                        "start_line": 1,
                        "end_line": 1,
                    },
                }
                (self.corpus / "ground-truth" / "records" / f"{instance_id}.json").write_text(
                    json.dumps(record), encoding="utf-8"
                )
                targets.append(instance_id)

        for number in range(1, 11):
            instance_id = f"OB-{number:02d}"
            record = {
                "instance_id": instance_id,
                "anti_pattern": "ObsoleteApiUsage",
                "location": {
                    "file": f"src/{instance_id}/Target.cs",
                    "symbol": f"{instance_id}.Target",
                    "start_line": 1,
                    "end_line": 1,
                },
            }
            (self.corpus / "ground-truth" / "records" / f"{instance_id}.json").write_text(
                json.dumps(record), encoding="utf-8"
            )

        manifest = {
            "corpus_version": "v2.0",
            "release_status": "candidate_pending_human_review",
            "frozen_at": None,
            "totals": {"god_class": 13, "long_method": 13, "obsolete_api": 10},
        }
        (self.corpus / "ground-truth" / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        agreement = {
            "summary": {"instances_checked": 36, "agreed": 36, "disagreed": 0},
            "release_gate_passed": True,
        }
        (self.corpus / "ground-truth" / "band-agreement-v2.0.json").write_text(
            json.dumps(agreement), encoding="utf-8"
        )
        self._write_review("r1", True)
        self._write_review("r2", True)

        plan = {
            "version": "2.0.0",
            "evaluated_target_count": 26,
            "cases_per_evaluated_target": 10,
            "obsolete_smoke_case_count": 10,
            "expected_golden_file_count": 270,
        }
        (self.pipeline / "layer3" / "ORACLE_PLAN_V2.json").write_text(
            json.dumps(plan), encoding="utf-8"
        )
        for instance_id in targets:
            for number in range(1, 11):
                (self.pipeline / "layer3" / "golden" / f"{instance_id}.P{number:02d}.golden").write_text(
                    "ok\n", encoding="utf-8"
                )
        for number in range(1, 11):
            (self.pipeline / "layer3" / "golden" / f"OB-{number:02d}.smoke.golden").write_text(
                "ok\n", encoding="utf-8"
            )

    def tearDown(self):
        self.temp.cleanup()

    def _write_review(self, rater: str, verdict):
        instances = [
            {"instance_id": f"{prefix}-{number:02d}", "valid": verdict, "semantic_note": "reviewed"}
            for prefix in ("GC", "LM")
            for number in range(11, 14)
        ]
        path = self.corpus / "ground-truth" / f"{rater}-worksheet-v2.0.json"
        path.write_text(json.dumps({"rater_id": rater.upper(), "instances": instances}), encoding="utf-8")

    def test_builds_the_fixed_26_by_3_by_8_design(self):
        spec = build_run_spec(
            self.corpus,
            self.pipeline,
            corpus_revision="a" * 40,
            pipeline_revision="b" * 40,
            model_name="gpt-5.6-sol",
            randomization_seed=20260812,
        )

        self.assertEqual(26, spec["design"]["evaluated_targets"])
        self.assertEqual(624, spec["design"]["factorial_assignments"])
        self.assertEqual(156, spec["design"]["hybrid_comparator_attempts"])
        self.assertEqual(5, spec["visible_tests"]["cases_per_target"])
        self.assertEqual(270, spec["private_oracle"]["total_cases"])
        self.assertEqual(26, len(spec["targets"]))

    def test_blank_human_verdict_blocks_release_and_campaign(self):
        self._write_review("r2", None)

        report = assess_readiness(self.corpus, self.pipeline)

        self.assertFalse(report["final_release_ready"])
        self.assertFalse(report["campaign_ready"])
        self.assertIn("r2_semantic_review_complete", report["failed_gates"])

    def test_complete_agreeing_reviews_and_oracle_pass(self):
        report = assess_readiness(self.corpus, self.pipeline)

        self.assertTrue(report["final_release_ready"])
        self.assertTrue(report["campaign_ready"])
        self.assertEqual([], report["failed_gates"])

    def test_rater_disagreement_is_a_hard_stop(self):
        self._write_review("r2", False)

        report = assess_readiness(self.corpus, self.pipeline)

        self.assertFalse(report["campaign_ready"])
        self.assertIn("semantic_review_agreement", report["failed_gates"])


if __name__ == "__main__":
    unittest.main()
