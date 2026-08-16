import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import analysis.confirmatory_v2_figures as figures


class ConfirmatoryV2FigureTests(unittest.TestCase):
    def test_population_note_reports_independent_targets_and_assignments(self):
        attempts = [
            {"instance_key": target}
            for target in ("GC-01", "LM-01")
            for _ in range(24)
        ]

        note = figures.campaign_population_note(attempts)

        self.assertEqual(
            "2 independent targets · 48 assigned repairs",
            note,
        )

    def test_script_help_runs_from_repository_root(self):
        completed = subprocess.run(
            [sys.executable, "analysis/confirmatory_v2_figures.py", "--help"],
            text=True, capture_output=True, check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)

    def test_campaign_figure_generator_exists(self):
        self.assertIsNotNone(
            importlib.util.find_spec("analysis.confirmatory_v2_figures"),
            "campaign-specific figure generator is not implemented",
        )

    def test_arm_summary_keeps_unavailable_separate_from_regression(self):
        summarise = getattr(figures, "summarise_attempt_arms", None)
        self.assertIsNotNone(summarise, "attempt-arm summary is not implemented")
        common = {
            "grounding_enabled": False,
            "control_structure": "single_shot",
            "visible_tests_enabled": True,
            "build_passed": True,
            "metric_resolved": True,
        }
        attempts = [
            {**common, "strict_success": True, "private_test_passed": True},
            {**common, "strict_success": False, "private_test_passed": False},
            {**common, "strict_success": False, "private_test_passed": None,
             "build_passed": False, "metric_resolved": False},
        ]

        rows = summarise(attempts)

        self.assertEqual(1, len(rows))
        self.assertEqual(1, rows[0]["strict_success"])
        self.assertEqual(1, rows[0]["private_regression"])
        self.assertEqual(1, rows[0]["unavailable"])

    def test_quality_loader_uses_sealed_artifact_assignment(self):
        load = getattr(figures, "load_quality_rows", None)
        self.assertIsNotNone(load, "quality-result loader is not implemented")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact = root / "artifact.json"
            artifact.write_text(json.dumps({
                "artifact_id": "a1",
                "grounding_enabled": True,
                "control_structure": "iterative",
                "visible_tests_enabled": False,
            }), encoding="utf-8")
            quality = root / "quality.jsonl"
            quality.write_text(json.dumps({
                "artifact_id": "a1",
                "artifact_ref": str(artifact),
                "smell_total_before": 36,
                "smell_total_after": 35,
                "ca_all_before": 263,
                "ca_all_after": 262,
            }) + "\n", encoding="utf-8")

            rows = load(quality)

        self.assertEqual((1, 1, 0), rows[0]["arm"])
        self.assertEqual(-1, rows[0]["smell_delta"])
        self.assertEqual(-1, rows[0]["ca_all_delta"])

    def test_generator_emits_current_thesis_figure_set(self):
        generate = getattr(figures, "generate_figures", None)
        self.assertIsNotNone(generate, "figure generation entry point is not implemented")
        attempts = []
        for instance in ("a", "b"):
            for grounding in (False, True):
                for control in ("single_shot", "iterative"):
                    for visible in (False, True):
                        for repetition in range(3):
                            attempts.append({
                                "instance_key": instance,
                                "grounding_enabled": grounding,
                                "control_structure": control,
                                "visible_tests_enabled": visible,
                                "strict_success": True,
                                "build_passed": True,
                                "metric_resolved": True,
                                "private_test_passed": True,
                            })
        contrast_names = [
            "visible_test_main", "grounding_main", "iteration_main",
            "test_effect__grounding_0__control_0",
            "test_effect__grounding_0__control_1",
            "test_effect__grounding_1__control_0",
            "test_effect__grounding_1__control_1",
        ]
        contrasts = [{
            "contrast": name, "estimate": 0.0, "ci95_lo": -0.1,
            "ci95_hi": 0.1, "exact_signflip_p": 1.0,
            "holm_adjusted_p": 1.0,
        } for name in contrast_names]
        quality = [
            {"arm": (grounding, iterative, visible), "smell_delta": -1,
             "ca_all_delta": 0}
            for grounding in (0, 1)
            for iterative in (0, 1)
            for visible in (0, 1)
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            generated = generate(attempts, contrasts, quality, root)

            expected = {
                "fig4_grounding_main_effect",
                "fig4_h2b_context",
                "figure5_2_strict_success_ladder",
                "figure5_3_grounding_control_interaction",
                "figure5_5_triggering_metric_reduction",
                "figure5_6_whole_solution_quality",
                "figure5_7_layer3_behavior",
                "figure5_8_visible_test_effect",
            }
            self.assertEqual(expected, set(generated))
            for name in expected:
                for extension in ("png", "svg", "pdf"):
                    self.assertTrue((root / "figures" / f"{name}.{extension}").is_file())

            grounding_svg = (
                root / "figures" / "fig4_grounding_main_effect.svg"
            ).read_text(encoding="utf-8")
            self.assertIn("2 independent targets", grounding_svg)
            self.assertIn("48 assigned repairs", grounding_svg)
            self.assertNotIn("19 independent targets", grounding_svg)

    def test_metric_resolution_uses_point_intervals_on_truncated_axis(self):
        geometry = getattr(figures, "metric_resolution_geometry", None)
        self.assertIsNotNone(geometry, "metric-resolution geometry is not declared")
        self.assertEqual("point_interval", geometry())
        limits = getattr(figures, "metric_resolution_xlim", None)
        self.assertIsNotNone(limits, "metric-resolution limits are not declared")
        self.assertGreater(limits()[1], 102)

    def test_layer3_tail_label_keeps_small_categories_readable(self):
        formatter = getattr(figures, "layer3_tail_label", None)
        self.assertIsNotNone(formatter, "Layer 3 tail-label formatter is not implemented")
        self.assertEqual("1 regression · 1 unavailable", formatter(1, 1))


if __name__ == "__main__":
    unittest.main()
