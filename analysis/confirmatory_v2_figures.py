"""Figures derived from the sealed 26-target confirmatory campaign."""

from __future__ import annotations

from collections import Counter
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import t as student_t

try:
    from analysis.factorial_test_feedback_analysis import build_cube
except ModuleNotFoundError:  # Direct execution: python analysis/confirmatory_v2_figures.py
    from factorial_test_feedback_analysis import build_cube


INK = "#17212B"
MUTED = "#607080"
GRID = "#D9E0E6"
BLUE = "#356AA0"
TEAL = "#16877A"
PURPLE = "#7656A3"
AMBER = "#D28C28"
RED = "#B94A48"
LIGHT = "#CED6DE"
ARM_ORDER = [
    (0, 0, 0), (0, 0, 1), (1, 0, 0), (1, 0, 1),
    (0, 1, 0), (0, 1, 1), (1, 1, 0), (1, 1, 1),
]


def arm_key(row: dict) -> tuple[int, int, int]:
    return (
        int(bool(row["grounding_enabled"])),
        int(row["control_structure"] == "iterative"),
        int(bool(row["visible_tests_enabled"])),
    )


def campaign_population_note(attempts: list[dict]) -> str:
    targets = {row["instance_key"] for row in attempts}
    return f"{len(targets)} independent targets · {len(attempts)} assigned repairs"


def outcome_category(row: dict) -> str:
    if row.get("private_test_passed") is None:
        return "unavailable"
    if row.get("strict_success") is True:
        return "strict_success"
    if row.get("build_passed") is not True:
        return "build_failed"
    if row.get("metric_resolved") is not True:
        return "metric_unresolved"
    if row.get("private_test_passed") is False:
        return "private_regression"
    return "other_failure"


def summarise_attempt_arms(attempts: list[dict]) -> list[dict]:
    grouped: dict[tuple[int, int, int], list[dict]] = {}
    for row in attempts:
        grouped.setdefault(arm_key(row), []).append(row)
    result = []
    for (grounding, iterative, visible), rows in sorted(grouped.items()):
        counts = Counter(outcome_category(row) for row in rows)
        result.append({
            "grounding": grounding,
            "iterative": iterative,
            "visible_test": visible,
            "assigned": len(rows),
            "strict_success": counts["strict_success"],
            "private_regression": counts["private_regression"],
            "metric_unresolved": counts["metric_unresolved"],
            "build_failed": counts["build_failed"],
            "unavailable": counts["unavailable"],
            "other_failure": counts["other_failure"],
        })
    return result


def load_quality_rows(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        quality = json.loads(line)
        artifact = json.loads(Path(quality["artifact_ref"]).read_text(encoding="utf-8-sig"))
        if artifact["artifact_id"] != quality["artifact_id"]:
            raise ValueError(f"quality/artifact identity mismatch: {quality['artifact_id']}")
        rows.append({
            **quality,
            "arm": arm_key(artifact),
            "smell_delta": quality["smell_total_after"] - quality["smell_total_before"],
            "ca_all_delta": quality["ca_all_after"] - quality["ca_all_before"],
        })
    return rows


def arm_label(arm: tuple[int, int, int]) -> str:
    grounding, iterative, visible = arm
    return (
        f"{'Grounded' if grounding else 'Ungrounded'} · "
        f"{'iterative' if iterative else 'single-shot'} · "
        f"tests {'ON' if visible else 'OFF'}"
    )


def cluster_ci(values: np.ndarray) -> tuple[float, float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    mean = float(np.mean(values))
    if len(values) < 2:
        return mean, mean, mean
    se = float(np.std(values, ddof=1) / np.sqrt(len(values)))
    half = float(student_t.ppf(0.975, len(values) - 1) * se)
    return mean, max(0.0, mean - half), min(1.0, mean + half)


def save_figure(fig, figures: Path, name: str) -> None:
    figures.mkdir(parents=True, exist_ok=True)
    fig.savefig(figures / f"{name}.png", dpi=300, bbox_inches="tight")
    fig.savefig(figures / f"{name}.svg", bbox_inches="tight")
    fig.savefig(figures / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def configure_style() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 9.5,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK,
        "axes.titlecolor": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.7,
        "axes.axisbelow": True,
    })


def plot_strict_ladder(attempts: list[dict], figures: Path) -> None:
    summaries = {(
        row["grounding"], row["iterative"], row["visible_test"]
    ): row for row in summarise_attempt_arms(attempts)}
    categories = [
        ("strict_success", "Strict success", TEAL),
        ("private_regression", "Behavioural regression", RED),
        ("metric_unresolved", "Metric unresolved", AMBER),
        ("build_failed", "Build/API failure", LIGHT),
        ("unavailable", "Unavailable", INK),
    ]
    fig, ax = plt.subplots(figsize=(10.4, 5.7))
    for y, arm in enumerate(ARM_ORDER):
        row = summaries[arm]
        left = 0.0
        for field, label, colour in categories:
            value = 100 * row[field] / row["assigned"]
            ax.barh(y, value, left=left, color=colour, height=0.68,
                    label=label if y == 0 else None)
            if value >= 3:
                ax.text(left + value / 2, y, str(row[field]), ha="center", va="center",
                        color="white" if field in {"strict_success", "private_regression", "unavailable"} else INK,
                        fontsize=8.5, fontweight="bold")
            left += value
    ax.set_yticks(range(len(ARM_ORDER)), [arm_label(arm) for arm in ARM_ORDER])
    ax.invert_yaxis(); ax.set_xlim(0, 100)
    ax.set_xlabel(
        f"Share of assigned repairs (%) · n=78 per arm · {campaign_population_note(attempts)}"
    )
    ax.set_title("Strict-success gate outcomes by factorial arm", fontweight="bold")
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save_figure(fig, figures, "figure5_2_strict_success_ladder")


def plot_interaction(attempts: list[dict], figures: Path) -> None:
    _, cube = build_cube(attempts, "strict_success")
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.7), sharey=True)
    for visible, ax in enumerate(axes):
        for grounding, colour, marker in ((0, BLUE, "o"), (1, TEAL, "s")):
            means, lows, highs = [], [], []
            for iterative in (0, 1):
                mean, low, high = cluster_ci(cube[:, grounding, iterative, visible])
                means.append(100 * mean); lows.append(100 * low); highs.append(100 * high)
            x = np.arange(2)
            ax.errorbar(x, means,
                        yerr=[[m - l for m, l in zip(means, lows)],
                              [h - m for m, h in zip(means, highs)]],
                        color=colour, marker=marker, capsize=4, linewidth=2,
                        label="Grounded" if grounding else "Ungrounded")
        ax.set_xticks([0, 1], ["Single-shot", "Iterative"])
        ax.set_title(f"Visible tests {'ON' if visible else 'OFF'}", fontweight="bold")
        ax.set_ylim(60, 103); ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("Strict success (%)")
    axes[1].legend(frameon=False, loc="lower right")
    fig.suptitle(
                 "Grounding × control interaction by visible-test assignment\n"
                 + campaign_population_note(attempts),
                 fontweight="bold", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    save_figure(fig, figures, "figure5_3_grounding_control_interaction")


def plot_metric_resolution(attempts: list[dict], figures: Path) -> None:
    _, cube = build_cube(attempts, "metric_resolved")
    means, lows, highs = [], [], []
    for arm in ARM_ORDER:
        mean, low, high = cluster_ci(cube[:, arm[0], arm[1], arm[2]])
        means.append(100 * mean); lows.append(100 * low); highs.append(100 * high)
    y = np.arange(len(ARM_ORDER))
    fig, ax = plt.subplots(figsize=(9.5, 5.5))
    for yi, (arm, mean, low, high) in enumerate(zip(ARM_ORDER, means, lows, highs)):
        colour = TEAL if arm[0] else BLUE
        ax.errorbar(mean, yi, xerr=[[mean - low], [high - mean]],
                    fmt="o", color=colour, ecolor=colour, capsize=4, markersize=7)
        ax.text(high + 0.5, yi, f"{mean:.1f}%", va="center", fontsize=8.5, color=MUTED)
    ax.set_yticks(y, [arm_label(arm) for arm in ARM_ORDER]); ax.invert_yaxis()
    ax.set_xlim(*metric_resolution_xlim())
    ax.set_xlabel(
        "Repairs resolving the triggering detector (%) · "
        + campaign_population_note(attempts)
    )
    ax.set_title("Triggering-metric resolution by factorial arm", fontweight="bold")
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    save_figure(fig, figures, "figure5_5_triggering_metric_reduction")


def metric_resolution_geometry() -> str:
    return "point_interval"


def metric_resolution_xlim() -> tuple[float, float]:
    return 65.0, 104.0


def quality_summary(quality: list[dict]) -> list[dict]:
    result = []
    for arm in ARM_ORDER:
        rows = [row for row in quality if tuple(row["arm"]) == arm]
        deltas = [row["smell_delta"] for row in rows]
        result.append({
            "arm": arm,
            "n": len(rows),
            "smell_improved": sum(value < 0 for value in deltas),
            "smell_same": sum(value == 0 for value in deltas),
            "smell_worse": sum(value > 0 for value in deltas),
            "ca_all_mean": float(np.mean([row["ca_all_delta"] for row in rows])),
        })
    return result


def plot_quality(quality: list[dict], figures: Path) -> None:
    summaries = quality_summary(quality)
    y = np.arange(len(summaries))
    fig, (left, right) = plt.subplots(1, 2, figsize=(12.0, 5.8), sharey=True,
                                      gridspec_kw={"width_ratios": [1.35, 1]})
    starts = np.zeros(len(summaries))
    for field, label, colour in (
        ("smell_improved", "Improved", TEAL),
        ("smell_same", "Unchanged", LIGHT),
        ("smell_worse", "Worsened", RED),
    ):
        values = np.array([100 * row[field] / row["n"] for row in summaries])
        left.barh(y, values, left=starts, color=colour, height=0.64, label=label)
        starts += values
    left.set_yticks(y, [arm_label(row["arm"]) for row in summaries]); left.invert_yaxis()
    left.set_xlim(0, 100); left.set_xlabel("Targeted-smell outcome (%)")
    left.set_title("Targeted detector", fontweight="bold"); left.grid(axis="y", visible=False)
    left.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.13))
    ca = [row["ca_all_mean"] for row in summaries]
    colours = [TEAL if value < 0 else RED if value > 0 else LIGHT for value in ca]
    right.barh(y, ca, color=colours, height=0.64)
    right.axvline(0, color=INK, linewidth=1)
    right.set_xlabel("Mean change in all analyser findings")
    right.set_title("Whole-solution analyser", fontweight="bold")
    right.grid(axis="y", visible=False)
    for yi, (value, row) in enumerate(zip(ca, summaries)):
        right.text(value + (0.03 if value >= 0 else -0.03), yi,
                   f"{value:+.2f} (n={row['n']})",
                   ha="left" if value >= 0 else "right", va="center", fontsize=8)
    fig.suptitle(
        f"Layer 2 structural-quality outcomes\n{len(quality)} materialised repairs",
        fontweight="bold", fontsize=13,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    save_figure(fig, figures, "figure5_6_whole_solution_quality")


def plot_layer3(attempts: list[dict], figures: Path) -> None:
    groups = {arm: [row for row in attempts if arm_key(row) == arm] for arm in ARM_ORDER}
    y = np.arange(len(ARM_ORDER)); starts = np.zeros(len(ARM_ORDER))
    fig, ax = plt.subplots(figsize=(9.8, 5.5))
    fields = [
        ("preserved", TEAL, lambda row: row.get("private_test_passed") is True),
        ("regression", RED, lambda row: row.get("private_test_passed") is False),
        ("unavailable", INK, lambda row: row.get("private_test_passed") is None),
    ]
    category_counts = {}
    for label, colour, predicate in fields:
        values = np.array([sum(predicate(row) for row in groups[arm]) for arm in ARM_ORDER])
        category_counts[label] = values
        ax.barh(y, values, left=starts, color=colour, height=0.64, label=label.capitalize())
        for yi, (start, value) in enumerate(zip(starts, values)):
            if value >= 3 or label == "preserved":
                ax.text(start + value / 2, yi, str(value), ha="center", va="center",
                        color="white", fontweight="bold", fontsize=8.5)
        starts += values
    for yi, (regression, unavailable) in enumerate(zip(
        category_counts["regression"], category_counts["unavailable"]
    )):
        label = layer3_tail_label(int(regression), int(unavailable))
        if label and regression + unavailable < 3:
            ax.text(78.4, yi, label, va="center", ha="left", fontsize=8.2, color=MUTED)
    ax.set_yticks(y, [arm_label(arm) for arm in ARM_ORDER]); ax.invert_yaxis()
    ax.set_xlim(0, 86)
    ax.set_xlabel(f"Assigned repairs (n=78 per arm) · {campaign_population_note(attempts)}")
    ax.set_title("Layer 3 behavioural preservation by factorial arm", fontweight="bold")
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save_figure(fig, figures, "figure5_7_layer3_behavior")


def layer3_tail_label(regressions: int, unavailable: int) -> str:
    parts = []
    if regressions:
        parts.append(f"{regressions} regression" + ("s" if regressions != 1 else ""))
    if unavailable:
        parts.append(f"{unavailable} unavailable")
    return " · ".join(parts)


def plot_visible_effects(contrasts: list[dict], attempts: list[dict], figures: Path) -> None:
    names = [
        "visible_test_main",
        "test_effect__grounding_0__control_0",
        "test_effect__grounding_0__control_1",
        "test_effect__grounding_1__control_0",
        "test_effect__grounding_1__control_1",
    ]
    labels = [
        "Main effect",
        "Ungrounded · single-shot",
        "Ungrounded · iterative",
        "Grounded · single-shot",
        "Grounded · iterative",
    ]
    lookup = {row["contrast"]: row for row in contrasts}
    rows = [lookup[name] for name in names]
    values = np.array([100 * float(row["estimate"]) for row in rows])
    lows = np.array([100 * float(row["ci95_lo"]) for row in rows])
    highs = np.array([100 * float(row["ci95_hi"]) for row in rows])
    y = np.arange(len(rows))
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.errorbar(values, y, xerr=[values - lows, highs - values], fmt="o",
                color=BLUE, ecolor=BLUE, capsize=4, markersize=7)
    ax.plot(values[0], y[0], "o", color=TEAL, markersize=9)
    ax.axvline(0, color=INK, linewidth=1)
    ax.set_xlim(float(np.min(lows) - 2), float(np.max(highs) + 6))
    ax.set_yticks(y, labels); ax.invert_yaxis()
    ax.set_xlabel("Visible-test effect on strict success (percentage points)")
    ax.set_title(
        "Paired visible-test effects with 95% cluster intervals\n"
        + campaign_population_note(attempts),
        fontweight="bold",
    )
    ax.grid(axis="y", visible=False)
    for yi, (value, row) in enumerate(zip(values, rows)):
        p_value = float(row.get("holm_adjusted_p") or row["exact_signflip_p"])
        ax.text(highs[yi] + 0.5, yi, f"{value:+.2f} pp · p={p_value:.3g}",
                va="center", fontsize=8.5, color=MUTED)
    fig.tight_layout()
    save_figure(fig, figures, "figure5_8_visible_test_effect")


def plot_grounding_main_effect(attempts: list[dict], figures: Path) -> None:
    _, cube = build_cube(attempts, "strict_success")
    target_rates = np.mean(cube, axis=(2, 3))
    estimates = [cluster_ci(target_rates[:, grounding]) for grounding in (0, 1)]
    means = np.array([100 * item[0] for item in estimates])
    lows = np.array([100 * item[1] for item in estimates])
    highs = np.array([100 * item[2] for item in estimates])
    difference = means[1] - means[0]

    fig, ax = plt.subplots(figsize=(7.4, 4.8))
    x = np.arange(2)
    ax.bar(x, means, color=[BLUE, TEAL], width=0.58)
    ax.errorbar(
        x, means, yerr=[means - lows, highs - means], fmt="none",
        ecolor=INK, capsize=5, linewidth=1.4,
    )
    ax.set_xticks(x, ["Ungrounded", "Grounded"])
    ax.set_ylim(0, 105)
    ax.set_ylabel("Strict success (%)")
    ax.set_title(
        "Grounding main effect on strict success\n"
        f"Grounded − ungrounded: {difference:+.2f} percentage points · "
        + campaign_population_note(attempts),
        fontweight="bold",
    )
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    save_figure(fig, figures, "fig4_grounding_main_effect")
    for extension in ("png", "svg", "pdf"):
        shutil.copy2(
            figures / f"fig4_grounding_main_effect.{extension}",
            figures / f"fig4_h2b_context.{extension}",
        )


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialised = []
    for row in rows:
        serialised.append({
            key: "|".join(map(str, value)) if isinstance(value, tuple) else value
            for key, value in row.items()
        })
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(serialised[0]))
        writer.writeheader(); writer.writerows(serialised)


def generate_figures(attempts: list[dict], contrasts: list[dict], quality: list[dict],
                     output: Path) -> list[str]:
    configure_style()
    figures = output / "figures"
    source = output / "source-data"
    source.mkdir(parents=True, exist_ok=True)
    write_csv(source / "attempt_arm_summary.csv", summarise_attempt_arms(attempts))
    write_csv(source / "quality_arm_summary.csv", quality_summary(quality))
    write_csv(source / "visible_test_effects.csv", [
        row for row in contrasts if row["contrast"] == "visible_test_main"
        or row["contrast"].startswith("test_effect__")
    ])
    plot_strict_ladder(attempts, figures)
    plot_interaction(attempts, figures)
    plot_metric_resolution(attempts, figures)
    plot_quality(quality, figures)
    plot_layer3(attempts, figures)
    plot_visible_effects(contrasts, attempts, figures)
    plot_grounding_main_effect(attempts, figures)
    return [
        "fig4_grounding_main_effect",
        "fig4_h2b_context",
        "figure5_2_strict_success_ladder",
        "figure5_3_grounding_control_interaction",
        "figure5_5_triggering_metric_reduction",
        "figure5_6_whole_solution_quality",
        "figure5_7_layer3_behavior",
        "figure5_8_visible_test_effect",
    ]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts", required=True, type=Path)
    parser.add_argument("--contrasts", required=True, type=Path)
    parser.add_argument("--quality", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    attempts = json.loads(args.attempts.read_text(encoding="utf-8-sig"))
    with args.contrasts.open(newline="", encoding="utf-8-sig") as handle:
        contrasts = list(csv.DictReader(handle))
    quality = load_quality_rows(args.quality)
    names = generate_figures(attempts, contrasts, quality, args.out)
    manifest = {
        "status": "complete",
        "attempts": len(attempts),
        "quality_rows": len(quality),
        "attempts_sha256": sha256(args.attempts),
        "contrasts_sha256": sha256(args.contrasts),
        "quality_sha256": sha256(args.quality),
        "generated_figures": names,
        "formats": ["png", "svg", "pdf"],
        "scope_note": (
            "Figures 5.2, 5.3, 5.5, 5.6, 5.7 and 5.8 depend on the new confirmatory "
            "campaign and were regenerated. The grounding summary and its compatibility "
            "alias were also regenerated. The architecture is generated separately; the "
            "illustrative trajectory and separate four-level context figure are unchanged."
        ),
    }
    (args.out / "FIGURE_REGENERATION_MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
