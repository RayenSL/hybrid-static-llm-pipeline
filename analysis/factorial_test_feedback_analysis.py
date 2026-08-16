"""Instance-clustered analysis for the frozen 2x2x2 test-feedback experiment.

Input is the canonical attempts.json emitted by HybridLens.CLI factorial-summary.
The independent unit is the anti-pattern instance (n=19); the three model
generations are averaged within instance and factorial cell. This matches the
estimands used by the frozen Monte Carlo power analysis.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from fractions import Fraction
from functools import reduce
from pathlib import Path

import numpy as np
from scipy.stats import t as student_t


CELLS = [(g, c, t) for g in (0, 1) for c in (0, 1) for t in (0, 1)]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"refusing to write empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def cell(control: str) -> int:
    if control == "single_shot":
        return 0
    if control == "iterative":
        return 1
    raise ValueError(f"unexpected control structure: {control}")


def build_cube(attempts: list[dict], field: str) -> tuple[list[str], np.ndarray]:
    instances = sorted({row["instance_key"] for row in attempts})
    if not instances:
        raise ValueError("factorial data contains no independent instances")
    by_instance = {name: i for i, name in enumerate(instances)}
    values: dict[tuple[int, int, int, int], list[float]] = {}
    for row in attempts:
        key = (
            by_instance[row["instance_key"]],
            int(row["grounding_enabled"]),
            cell(row["control_structure"]),
            int(row["visible_tests_enabled"]),
        )
        value = row.get(field)
        values.setdefault(key, []).append(float(value) if value is not None else math.nan)
    cube = np.empty((len(instances), 2, 2, 2), dtype=float)
    for i in range(len(instances)):
        for g, c, t in CELLS:
            observed = values.get((i, g, c, t), [])
            if len(observed) != 3:
                raise ValueError(
                    f"expected three repetitions for instance={instances[i]}, "
                    f"cell={(g, c, t)}; found {len(observed)}"
                )
            cube[i, g, c, t] = float(np.mean(observed))
    return instances, cube


def partition_private_outcomes(attempts: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    passes = [row for row in attempts if row.get("private_test_passed") is True]
    regressions = [row for row in attempts if row.get("private_test_passed") is False]
    unavailable = [row for row in attempts if row.get("private_test_passed") is None]
    return passes, regressions, unavailable


def exact_signflip_p_dynamic_programming(differences: np.ndarray) -> float:
    """Two-sided exact cluster sign-flip p-value without enumerating 2^n rows."""
    finite = np.asarray(differences, dtype=float)
    finite = finite[np.isfinite(finite)]
    if not len(finite) or np.all(finite == 0.0):
        return 1.0

    fractions = [Fraction(float(value)).limit_denominator(1_000_000) for value in finite]
    denominator = math.lcm(*(value.denominator for value in fractions))
    integers = [value.numerator * (denominator // value.denominator) for value in fractions]
    divisor = reduce(math.gcd, (abs(value) for value in integers if value), 0) or 1
    integers = [value // divisor for value in integers]

    distribution = Counter({0: 1})
    for value in integers:
        updated = Counter()
        for total, count in distribution.items():
            updated[total + value] += count
            updated[total - value] += count
        distribution = updated

    observed = abs(sum(integers))
    extreme = sum(count for total, count in distribution.items() if abs(total) >= observed)
    return extreme / (1 << len(integers))


def exact_signflip_p(differences: np.ndarray) -> float:
    return exact_signflip_p_dynamic_programming(differences)


def estimate(differences: np.ndarray) -> dict:
    differences = np.asarray(differences, dtype=float)
    differences = differences[np.isfinite(differences)]
    n = len(differences)
    if n < 2:
        raise ValueError("at least two complete instance-level differences are required")
    mean = float(np.mean(differences))
    se = float(np.std(differences, ddof=1) / math.sqrt(n))
    critical = float(student_t.ppf(0.975, n - 1))
    return {
        "n_instances": n,
        "estimate": mean,
        "ci95_lo": mean - critical * se,
        "ci95_hi": mean + critical * se,
        "cluster_se": se,
        "exact_signflip_p": exact_signflip_p(differences),
    }


def holm(rows: list[dict]) -> None:
    families: dict[str, list[dict]] = {}
    for row in rows:
        if row["holm_family"]:
            families.setdefault(row["holm_family"], []).append(row)
        else:
            row["holm_adjusted_p"] = row["exact_signflip_p"]
    for members in families.values():
        ordered = sorted(members, key=lambda row: row["exact_signflip_p"])
        running = 0.0
        m = len(ordered)
        for index, row in enumerate(ordered):
            adjusted = min(1.0, (m - index) * row["exact_signflip_p"])
            running = max(running, adjusted)
            row["holm_adjusted_p"] = running


def contrast_rows(cube: np.ndarray) -> list[dict]:
    specs: list[tuple[str, str, str, str, np.ndarray]] = []

    def weights() -> np.ndarray:
        return np.zeros((2, 2, 2), dtype=float)

    w = weights()
    w[:, :, 1] = 0.25
    w[:, :, 0] = -0.25
    specs.append(("visible_test_main", "test_on - test_off, averaged over grounding and control",
                  "confirmatory_primary", "", w))

    for g in (0, 1):
        for c in (0, 1):
            w = weights()
            w[g, c, 1], w[g, c, 0] = 1.0, -1.0
            specs.append((
                f"test_effect__grounding_{g}__control_{c}",
                f"test_on - test_off at grounding={g}, iterative={c}",
                "exploratory_underpowered",
                "cell_specific_test",
                w,
            ))

    w = weights()
    w[1, :, :] = 0.25
    w[0, :, :] = -0.25
    specs.append(("grounding_main", "grounded - ungrounded, averaged over control and test",
                  "planned_secondary", "", w))
    for c in (0, 1):
        for t in (0, 1):
            w = weights()
            w[1, c, t], w[0, c, t] = 1.0, -1.0
            specs.append((
                f"grounding_effect__control_{c}__test_{t}",
                f"grounded - ungrounded at iterative={c}, test={t}",
                "planned_secondary",
                "grounding_simple",
                w,
            ))

    w = weights()
    w[:, 1, :] = 0.25
    w[:, 0, :] = -0.25
    specs.append(("iteration_main", "iterative - single_shot, averaged over grounding and test",
                  "planned_secondary", "", w))
    for g in (0, 1):
        for t in (0, 1):
            w = weights()
            w[g, 1, t], w[g, 0, t] = 1.0, -1.0
            specs.append((
                f"iteration_effect__grounding_{g}__test_{t}",
                f"iterative - single_shot at grounding={g}, test={t}",
                "planned_secondary",
                "iteration_simple",
                w,
            ))

    w = weights()
    for g, c, t in CELLS:
        w[g, c, t] = 0.5 * (1 if g else -1) * (1 if t else -1)
    specs.append(("grounding_x_test", "difference in test effects: grounded - ungrounded, averaged over control",
                  "exploratory_underpowered", "test_interactions", w))
    w = weights()
    for g, c, t in CELLS:
        w[g, c, t] = 0.5 * (1 if c else -1) * (1 if t else -1)
    specs.append(("control_x_test", "difference in test effects: iterative - single_shot, averaged over grounding",
                  "exploratory_underpowered", "test_interactions", w))
    w = weights()
    for g, c, t in CELLS:
        w[g, c, t] = (1 if g else -1) * (1 if c else -1) * (1 if t else -1)
    specs.append(("grounding_x_control_x_test", "three-way difference-in-difference-in-differences",
                  "exploratory_underpowered", "test_interactions", w))

    rows = []
    for name, description, status, family, w in specs:
        differences = np.sum(cube * w[None, :, :, :], axis=(1, 2, 3))
        rows.append({
            "contrast": name,
            "description": description,
            "status": status,
            "holm_family": family,
            **estimate(differences),
        })
    holm(rows)
    return rows


def token_rows(token_cube: np.ndarray) -> list[dict]:
    rows = []
    specs = [("visible_test_main", None, None)]
    specs.extend(
        (f"test_effect__grounding_{g}__control_{c}", g, c)
        for g in (0, 1) for c in (0, 1)
    )
    for name, selected_g, selected_c in specs:
        if selected_g is None:
            differences = np.mean(
                token_cube[:, :, :, 1] - token_cube[:, :, :, 0], axis=(1, 2)
            )
        else:
            differences = (
                token_cube[:, selected_g, selected_c, 1]
                - token_cube[:, selected_g, selected_c, 0]
            )
        rows.append({"contrast": name, "unit": "repair_tokens", **estimate(differences)})
    return rows


def model_ready(attempts: list[dict], instances: list[str], path: Path) -> None:
    index = {name: i + 1 for i, name in enumerate(instances)}
    rows = []
    for row in attempts:
        g = int(row["grounding_enabled"])
        c = cell(row["control_structure"])
        t = int(row["visible_tests_enabled"])
        rows.append({
            "run_id": row["run_id"],
            "instance_id": index[row["instance_key"]],
            "instance_key": row["instance_key"],
            "anti_pattern_type": row["anti_pattern_type"],
            "god_class": int(row["anti_pattern_type"] == "god_class"),
            "grounding": g,
            "iterative": c,
            "visible_test": t,
            "grounding_x_iterative": g * c,
            "grounding_x_visible_test": g * t,
            "iterative_x_visible_test": c * t,
            "grounding_x_iterative_x_visible_test": g * c * t,
            "strict_success": int(row["strict_success"]),
            "build_passed": int(row["build_passed"]),
            "metric_resolved": int(row["metric_resolved"]),
            "private_test_passed": (
                int(row["private_test_passed"])
                if row.get("private_test_passed") is not None else None
            ),
            "total_tokens": row["total_tokens"],
        })
    write_csv(path, rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    attempts = json.loads(args.attempts.read_text(encoding="utf-8-sig"))
    instances = sorted({row["instance_key"] for row in attempts})
    expected_attempts = len(instances) * len(CELLS) * 3
    if len(attempts) != expected_attempts:
        raise ValueError(
            f"expected {expected_attempts} ITT attempts for {len(instances)} instances, "
            f"found {len(attempts)}"
        )
    args.out.mkdir(parents=True, exist_ok=False)

    instances, outcome_cube = build_cube(attempts, "strict_success")
    _, token_cube = build_cube(attempts, "total_tokens")
    contrasts = contrast_rows(outcome_cube)
    tokens = token_rows(token_cube)
    write_csv(args.out / "paired_risk_differences.csv", contrasts)
    write_csv(args.out / "paired_token_differences.csv", tokens)
    model_ready(attempts, instances, args.out / "model_ready_attempts.csv")

    private_passes, private_regression_rows, private_unavailable = partition_private_outcomes(attempts)
    regressions = [
        {
            "run_id": row["run_id"],
            "instance_key": row["instance_key"],
            "anti_pattern_type": row["anti_pattern_type"],
            "grounding_enabled": row["grounding_enabled"],
            "control_structure": row["control_structure"],
            "visible_tests_enabled": row["visible_tests_enabled"],
            "metric_resolved": row["metric_resolved"],
            "strict_success": row["strict_success"],
            "materialized_source_ref": row["materialized_source_ref"],
        }
        for row in private_regression_rows
    ]
    write_csv(args.out / "private_regressions.csv", regressions)
    unavailable_rows = [
        {
            "run_id": row["run_id"],
            "instance_key": row["instance_key"],
            "anti_pattern_type": row["anti_pattern_type"],
            "grounding_enabled": row["grounding_enabled"],
            "control_structure": row["control_structure"],
            "visible_tests_enabled": row["visible_tests_enabled"],
            "strict_success": row["strict_success"],
            "materialized_source_ref": row["materialized_source_ref"],
        }
        for row in private_unavailable
    ]
    if unavailable_rows:
        write_csv(args.out / "private_unavailable.csv", unavailable_rows)

    arm_private = Counter(
        (row["grounding_enabled"], row["control_structure"], row["visible_tests_enabled"])
        for row in private_regression_rows
    )
    metadata = {
        "analysis_status": "complete_for_prespecified_instance_level_paired_estimands",
        "attempts_sha256": sha256(args.attempts),
        "attempts": len(attempts),
        "independent_instances": len(instances),
        "repetitions_per_cell": 3,
        "strict_successes": sum(row["strict_success"] for row in attempts),
        "private_passes": len(private_passes),
        "private_regressions": len(regressions),
        "private_unavailable": len(private_unavailable),
        "method": {
            "aggregation": "three repetitions averaged within instance and factorial cell",
            "confidence_interval": f"paired instance-level Student-t interval, df={len(instances) - 1}",
            "hypothesis_test": (
                f"two-sided exact sign-flip randomization test over all 2^{len(instances)} "
                "cluster signs, evaluated by discrete dynamic programming"
            ),
            "multiplicity": "Holm adjustment within each four-cell simple-effect family and the three test-interaction family",
            "power_classification": "visible-test main effect confirmatory; cell-specific test effects and test interactions exploratory",
        },
        "private_regressions_by_arm": [
            {
                "grounding_enabled": g,
                "control_structure": c,
                "visible_tests_enabled": t,
                "regressions": count,
            }
            for (g, c, t), count in sorted(arm_private.items(), key=lambda item: str(item[0]))
        ],
        "mixed_effects_logistic_model": {
            "prespecified_formula": "strict_success ~ grounding * control_structure * visible_test + anti_pattern + (1 | instance)",
            "status": "model_ready_dataset_emitted; fit separately as a model-based sensitivity analysis",
            "interpretation_rule": "paired instance-level risk differences remain the primary effect-scale analysis",
        },
    }
    (args.out / "ANALYSIS_METADATA.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    primary = next(row for row in contrasts if row["contrast"] == "visible_test_main")
    report = [
        "# Factorial test-feedback analysis",
        "",
        f"- ITT attempts: {len(attempts)}",
        f"- Independent anti-pattern instances: {len(instances)}",
        f"- Strict successes: {metadata['strict_successes']}/{len(attempts)} "
        f"({metadata['strict_successes'] / len(attempts):.1%})",
        f"- Private behavioral passes: {metadata['private_passes']}/{len(attempts)} "
        f"({metadata['private_passes'] / len(attempts):.1%})",
        f"- Private behavioral regressions: {len(regressions)}/{len(attempts)}",
        f"- Private outcome unavailable after API failure: {len(private_unavailable)}/{len(attempts)}",
        "",
        "## Confirmatory primary estimand",
        "",
        f"Visible-test main effect (test ON minus OFF, averaged over grounding and control): "
        f"{primary['estimate'] * 100:+.2f} percentage points "
        f"(95% CI {primary['ci95_lo'] * 100:+.2f} to {primary['ci95_hi'] * 100:+.2f}; "
        f"exact cluster sign-flip p={primary['exact_signflip_p']:.6g}).",
        "",
        "Cell-specific test effects and interactions are retained as exploratory because the frozen "
        "power analysis classified them as underpowered. See paired_risk_differences.csv.",
        "",
        "## Prespecified mixed-effects model",
        "",
        "A model-ready attempt table is emitted for the prespecified random-intercept logistic "
        "sensitivity model. Its results are reported separately from the primary paired estimands.",
    ]
    (args.out / "PAIRED_ANALYSIS_REPORT.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
