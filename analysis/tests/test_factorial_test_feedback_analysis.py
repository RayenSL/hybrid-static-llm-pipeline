import unittest

import numpy as np
from scipy.stats import t

import analysis.factorial_test_feedback_analysis as analysis
from analysis.factorial_test_feedback_analysis import build_cube, estimate


def complete_attempts(instance_count: int = 26) -> list[dict]:
    rows = []
    for instance in range(instance_count):
        for grounding in (False, True):
            for control in ("single_shot", "iterative"):
                for visible in (False, True):
                    for repetition in range(1, 4):
                        rows.append({
                            "instance_key": f"instance-{instance:02d}",
                            "grounding_enabled": grounding,
                            "control_structure": control,
                            "visible_tests_enabled": visible,
                            "strict_success": repetition > 1,
                            "total_tokens": 100 + repetition,
                        })
    return rows


class FactorialTestFeedbackAnalysisTests(unittest.TestCase):
    def test_build_cube_accepts_complete_26_instance_design(self):
        instances, cube = build_cube(complete_attempts(), "strict_success")

        self.assertEqual(26, len(instances))
        self.assertEqual((26, 2, 2, 2), cube.shape)
        np.testing.assert_allclose(cube, 2 / 3)

    def test_estimate_uses_degrees_of_freedom_from_observed_clusters(self):
        differences = np.array([0.0, 1.0])

        result = estimate(differences)

        mean = float(np.mean(differences))
        se = float(np.std(differences, ddof=1) / np.sqrt(2))
        expected_half_width = float(t.ppf(0.975, 1) * se)
        self.assertAlmostEqual(mean - expected_half_width, result["ci95_lo"])
        self.assertAlmostEqual(mean + expected_half_width, result["ci95_hi"])

    def test_exact_sign_flip_uses_discrete_dynamic_programming(self):
        function = getattr(analysis, "exact_signflip_p_dynamic_programming", None)
        self.assertIsNotNone(function, "dynamic-programming exact test is not implemented")

        result = function(np.ones(26))

        self.assertAlmostEqual(2 / (2 ** 26), result)

    def test_token_cube_retains_unavailable_assignment_as_nan(self):
        attempts = complete_attempts()
        attempts[0]["total_tokens"] = None

        _, cube = build_cube(attempts, "total_tokens")

        self.assertTrue(np.isnan(cube[0, 0, 0, 0]))
        self.assertEqual(25, np.count_nonzero(np.isfinite(cube[:, 0, 0, 0])))

    def test_private_outcomes_distinguish_regression_from_unavailable(self):
        function = getattr(analysis, "partition_private_outcomes", None)
        self.assertIsNotNone(function, "private-outcome partition is not implemented")
        attempts = [
            {"private_test_passed": True},
            {"private_test_passed": False},
            {"private_test_passed": None},
        ]

        passes, regressions, unavailable = function(attempts)

        self.assertEqual(1, len(passes))
        self.assertEqual(1, len(regressions))
        self.assertEqual(1, len(unavailable))


if __name__ == "__main__":
    unittest.main()
