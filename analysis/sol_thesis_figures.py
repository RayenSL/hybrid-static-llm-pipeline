#!/usr/bin/env python3
"""Regenerate thesis figures that have valid GPT-5.6 Sol factorial equivalents."""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
from scipy.stats import t as student_t


INK = "#1a1a1a"
BODY = "#30363b"
MUTED = "#66707a"
GRID = "#d9dee2"
TEAL = "#2a8580"
BLUE = "#3977a8"
PURPLE = "#6f4c9b"
AMBER = "#d99000"
RED = "#cf4b45"
LGRAY = "#b8bdc2"
CREAM = "#fffaf3"

plt.rcParams.update({
    "font.size": 10.5,
    "font.family": "sans-serif",
    "axes.edgecolor": MUTED,
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titlesize": 12,
    "figure.dpi": 150,
    "svg.fonttype": "none",
})


def save(fig, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg", "pdf"):
        fig.savefig(
            out_dir / f"{name}.{extension}",
            dpi=300,
            bbox_inches="tight",
            facecolor="white",
        )
    plt.close(fig)
    print(f"wrote {name}.png/.svg/.pdf")


def ci(values, *, clip=False):
    values = np.asarray(values, dtype=float)
    mean = float(values.mean())
    if len(values) <= 1:
        return mean, mean, mean
    se = float(values.std(ddof=1) / np.sqrt(len(values)))
    half = float(student_t.ppf(0.975, len(values) - 1) * se)
    lo, hi = mean - half, mean + half
    if clip:
        lo, hi = max(0.0, lo), min(1.0, hi)
    return mean, lo, hi


def control_index(value: str) -> int:
    return 1 if value == "iterative" else 0


def build_cube(attempts, field):
    instances = sorted({row["instance_key"] for row in attempts})
    index = {key: i for i, key in enumerate(instances)}
    grouped = defaultdict(list)
    for row in attempts:
        grouped[(
            index[row["instance_key"]],
            int(row["grounding_enabled"]),
            control_index(row["control_structure"]),
            int(row["visible_tests_enabled"]),
        )].append(float(row[field]))
    cube = np.empty((len(instances), 2, 2, 2), dtype=float)
    for i in range(len(instances)):
        for g in (0, 1):
            for c in (0, 1):
                for t in (0, 1):
                    values = grouped[(i, g, c, t)]
                    if len(values) != 3:
                        raise ValueError("factorial cube is incomplete")
                    cube[i, g, c, t] = np.mean(values)
    return instances, cube


def arm_label(g, c, t):
    return (
        f"{'Grounded' if g else 'Ungrounded'} · "
        f"{'iterative' if c else 'single-shot'} · "
        f"test {'ON' if t else 'OFF'}"
    )


def arm_short(g, c):
    return f"{'Grounded' if g else 'Ungrounded'}\n{'iterative' if c else 'single-shot'}"


def fig1(cube, out_dir):
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.8), sharey=True, dpi=300)
    for t, ax in enumerate(axes):
        x = np.arange(4)
        cells = [(0, 0), (1, 0), (0, 1), (1, 1)]
        labels = [arm_short(g, c) for g, c in cells]
        means, los, his, colors = [], [], [], []
        for g, c in cells:
            mean, lo, hi = ci(cube[:, g, c, t], clip=True)
            means.append(100 * mean); los.append(100 * lo); his.append(100 * hi)
            colors.append(TEAL if g else BLUE)
        errors = [
            [value - lo for value, lo in zip(means, los)],
            [hi - value for value, hi in zip(means, his)],
        ]
        ax.bar(x, means, color=colors, width=0.62, zorder=3)
        ax.errorbar(x, means, yerr=errors, fmt="none", ecolor=INK, capsize=4, zorder=4)
        for xi, value in zip(x, means):
            ax.text(xi, min(103, value + 2), f"{value:.1f}%", ha="center", fontweight="bold")
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=9)
        ax.set_title(f"Visible characterization test {'ON' if t else 'OFF'}", fontweight="bold")
        ax.set_ylim(0, 108); ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("Strict success (%)")
    fig.suptitle("Strict success by grounding × control structure", fontweight="bold", fontsize=14)
    fig.text(
        0.5, 0.01,
        "Strict success = final build passed + detector metric resolved + private behavioral oracle passed",
        ha="center", color=MUTED, fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    save(fig, out_dir, "fig1_h1c_2x2")


def fig2(cube, out_dir):
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.5), sharey=True, dpi=300)
    for t, ax in enumerate(axes):
        for g, color, marker, label in (
            (0, BLUE, "s", "Ungrounded"),
            (1, TEAL, "o", "Grounded"),
        ):
            values, low, high = [], [], []
            for c in (0, 1):
                mean, lo, hi = ci(cube[:, g, c, t], clip=True)
                values.append(100 * mean); low.append(100 * lo); high.append(100 * hi)
            ax.errorbar(
                [0, 1], values,
                yerr=[[v - lo for v, lo in zip(values, low)],
                      [hi - v for v, hi in zip(values, high)]],
                color=color, marker=marker, ms=7, lw=2.2, capsize=4, label=label, zorder=3,
            )
            for x, value in enumerate(values):
                ax.annotate(f"{value:.1f}", (x, value), xytext=(0, 8),
                            textcoords="offset points", ha="center", color=color)
        ax.set_xticks([0, 1]); ax.set_xticklabels(["Single-shot", "Iterative"])
        ax.set_xlim(-0.25, 1.25); ax.set_ylim(65, 105)
        ax.set_title(f"Test {'ON' if t else 'OFF'}", fontweight="bold")
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("Strict success (%)")
    axes[1].legend(frameon=False, loc="lower right")
    fig.suptitle("Grounding × control interaction, stratified by visible-test assignment",
                 fontweight="bold", fontsize=13.5)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    save(fig, out_dir, "fig2_h1c_interaction")


def gate_category(row):
    if not row["build_passed"]:
        return "build_failed"
    if not row["metric_resolved"]:
        return "metric_unresolved"
    if not row["private_test_passed"]:
        return "private_regression"
    return "strict_success"


def fig3(attempts, out_dir):
    order = ["strict_success", "private_regression", "metric_unresolved", "build_failed"]
    colors = {
        "strict_success": TEAL,
        "private_regression": RED,
        "metric_unresolved": AMBER,
        "build_failed": LGRAY,
    }
    arms = [(g, c, t) for c in (0, 1) for g in (0, 1) for t in (0, 1)]
    distributions = {}
    for arm in arms:
        g, c, t = arm
        rows = [
            row for row in attempts
            if int(row["grounding_enabled"]) == g
            and control_index(row["control_structure"]) == c
            and int(row["visible_tests_enabled"]) == t
        ]
        distributions[arm] = Counter(gate_category(row) for row in rows)

    fig, ax = plt.subplots(figsize=(10.0, 6.0), dpi=300)
    for i, arm in enumerate(arms):
        left = 0
        for category in order:
            count = distributions[arm][category]
            percent = 100 * count / 57
            ax.barh(i, percent, left=left, color=colors[category], height=0.67, zorder=3)
            if percent >= 5:
                ax.text(left + percent / 2, i, str(count), ha="center", va="center",
                        color="white" if category in {"strict_success", "private_regression"} else INK,
                        fontweight="bold", fontsize=9)
            left += percent
    ax.set_yticks(range(len(arms)))
    ax.set_yticklabels([arm_label(*arm) for arm in arms], fontsize=9)
    ax.invert_yaxis(); ax.set_xlim(0, 100)
    ax.set_xlabel("Share of assigned attempts (%) · n=57 per arm")
    ax.set_title("Strict-success gate outcomes by factorial arm", fontweight="bold", pad=12)
    ax.legend(
        handles=[Patch(color=colors[key], label=key.replace("_", " ")) for key in order],
        ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12), fontsize=9,
    )
    ax.grid(axis="y", visible=False)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save(fig, out_dir, "fig3_ladder")


def fig4(cube, out_dir, tables_dir):
    rows = []
    for g in (0, 1):
        instance_values = cube[:, g, :, :].mean(axis=(1, 2))
        mean, lo, hi = ci(instance_values, clip=True)
        rows.append({
            "grounding": "grounded" if g else "ungrounded",
            "independent_instances": len(instance_values),
            "attempts": 228,
            "strict_success": mean,
            "ci95_lo": lo,
            "ci95_hi": hi,
        })
    with (tables_dir / "sol_grounding_main_effect.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    values = [100 * row["strict_success"] for row in rows]
    lows = [100 * row["ci95_lo"] for row in rows]
    highs = [100 * row["ci95_hi"] for row in rows]
    difference = values[1] - values[0]
    fig, ax = plt.subplots(figsize=(6.6, 4.7), dpi=300)
    x = np.arange(2)
    ax.bar(x, values, width=0.56, color=[BLUE, TEAL], zorder=3)
    ax.errorbar(
        x, values,
        yerr=[[v - lo for v, lo in zip(values, lows)],
              [hi - v for v, hi in zip(values, highs)]],
        fmt="none", ecolor=INK, capsize=4, zorder=4,
    )
    for xi, value in zip(x, values):
        ax.text(xi, min(103, value + 2), f"{value:.1f}%", ha="center",
                fontweight="bold")
    ax.annotate(
        f"paired main effect: +{difference:.2f} pp",
        xy=(0.5, 0.12), xycoords="axes fraction", ha="center",
        color=BODY, fontsize=10,
        bbox={"boxstyle": "round,pad=0.35", "facecolor": CREAM,
              "edgecolor": GRID},
    )
    ax.set_xticks(x)
    ax.set_xticklabels(["Ungrounded", "Grounded"])
    ax.set_ylabel("Strict success (%)")
    ax.set_ylim(0, 108)
    ax.set_title("Strict success by binary grounding assignment", fontweight="bold")
    ax.grid(axis="x", visible=False)
    fig.text(
        0.5, 0.01,
        "Control structure and visible-test assignment pooled · cluster CI over 19 independent targets",
        ha="center", color=MUTED, fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, out_dir, "fig4_grounding_main_effect")
    for extension in ("png", "svg", "pdf"):
        shutil.copy2(
            out_dir / f"fig4_grounding_main_effect.{extension}",
            out_dir / f"fig4_h2b_context.{extension}",
        )


def load_final_records(traces: Path):
    records = []
    for path in sorted(traces.glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        for row in rows:
            if row.get("control_structure") == "single_shot" and row.get("agentic_snapshot") is None:
                records.append(row)
            elif row.get("control_structure") == "iterative" and row.get("agentic_snapshot") == "final":
                records.append(row)
    if len(records) != 456:
        raise ValueError(f"expected 456 canonical trace rows, found {len(records)}")
    return records


def fig5(records, out_dir, tables_dir):
    agentic = [
        row for row in records
        if row["control_structure"] == "iterative" and not row["grounding_enabled"]
    ]
    instance_values = defaultdict(list)
    for row in agentic:
        key = (row["anti_pattern_type"], f"{row['file_path']}::{row['symbol_name']}::{row['line']}")
        instance_values[key].append(float(row.get("agentic_recovered") is True))
    rows = []
    for anti_pattern in ("long_method", "god_class"):
        clusters = [
            np.mean(values)
            for (kind, _instance), values in instance_values.items()
            if kind == anti_pattern
        ]
        mean, lo, hi = ci(clusters, clip=True)
        rows.append({
            "anti_pattern": anti_pattern,
            "independent_instances": len(clusters),
            "attempts": sum(
                len(values) for (kind, _), values in instance_values.items()
                if kind == anti_pattern
            ),
            "recall": mean,
            "ci95_lo": lo,
            "ci95_hi": hi,
        })
    with (tables_dir / "sol_agentic_recall.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)

    fig, ax = plt.subplots(figsize=(6.3, 4.5), dpi=300)
    x = np.arange(2)
    values = [100 * row["recall"] for row in rows]
    lows = [100 * row["ci95_lo"] for row in rows]
    highs = [100 * row["ci95_hi"] for row in rows]
    ax.bar(x, values, width=0.56, color=BLUE, zorder=3)
    ax.errorbar(
        x, values,
        yerr=[[v - lo for v, lo in zip(values, lows)],
              [hi - v for v, hi in zip(values, highs)]],
        fmt="none", ecolor=INK, capsize=4, zorder=4,
    )
    for i, (value, row) in enumerate(zip(values, rows)):
        ax.text(i, min(103, value + 3), f"{value:.1f}%\n(n={row['independent_instances']} instances)",
                ha="center", fontsize=9.5)
    ax.set_xticks(x); ax.set_xticklabels(["Long Method", "God Class"])
    ax.set_ylabel("Agentic target recovery (%)")
    ax.set_ylim(0, 108); ax.grid(axis="x", visible=False)
    ax.set_title("Ungrounded iterative diagnosis recall by anti-pattern", fontweight="bold")
    fig.text(0.5, 0.01, "Clustered by independent target; test-ON and test-OFF attempts pooled",
             ha="center", color=MUTED, fontsize=9)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    save(fig, out_dir, "fig5_recall")
    for extension in ("png", "svg", "pdf"):
        shutil.copy2(out_dir / f"fig5_recall.{extension}", out_dir / f"agentic_recall.{extension}")


def fig7(metric_path, out_dir):
    data = json.loads(metric_path.read_text(encoding="utf-8-sig"))
    series = data["series"]
    x = [row["iteration"] for row in series]
    cc = [row["cc"] for row in series]
    loc = [row["loc"] for row in series]
    builds = [row["build_ok"] for row in series]
    fig, left = plt.subplots(figsize=(8.2, 4.8), dpi=300)
    right = left.twinx()
    top = max(max(cc), data["cc_threshold"]) + 2
    left.axhspan(data["cc_threshold"], top, color=RED, alpha=0.07)
    left.axhline(data["cc_threshold"], color=RED, ls="--", lw=1.2)
    right.plot(x, loc, color=MUTED, ls=(0, (4, 2)), marker="s", lw=1.6)
    left.plot(x, cc, color=BLUE, lw=2.4)
    for xi, value, ok in zip(x, cc, builds):
        left.plot(xi, value, marker="o", ms=11, mfc=TEAL if ok else RED, mec="white", mew=1.4)
        left.annotate(str(value), (xi, value), xytext=(0, 13), textcoords="offset points",
                      ha="center", fontweight="bold", color=BLUE)
    left.set_xticks(x)
    left.set_xticklabels(["Original" if i == 0 else f"Edit {i}\nbuild {'pass' if builds[i] else 'fail'}" for i in x])
    left.set_ylabel("Cyclomatic complexity", color=BLUE)
    right.set_ylabel("Lines of code", color=MUTED)
    left.set_ylim(0, top); right.set_ylim(0, max(loc) + 12)
    left.set_title(
        "Illustrative Sol metric trajectory — AllocationCalculator.Allocate\n"
        "grounded iterative, test OFF, run 1",
        fontweight="bold",
    )
    left.legend(
        handles=[
            Line2D([0], [0], color=BLUE, marker="o", label="cyclomatic complexity"),
            Line2D([0], [0], color=MUTED, ls=(0, (4, 2)), marker="s", label="lines of code"),
            Line2D([0], [0], color=RED, ls="--", label="Long Method threshold"),
        ],
        frameon=False, loc="upper right", fontsize=9,
    )
    fig.tight_layout()
    save(fig, out_dir, "fig7_metric_trajectory_allocationcalculator")


def fig8(cube, out_dir):
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.7), sharey=True, dpi=300)
    for t, ax in enumerate(axes):
        cells = [(0, 0), (1, 0), (0, 1), (1, 1)]
        x = np.arange(4)
        values, lows, highs = [], [], []
        for g, c in cells:
            mean, lo, hi = ci(cube[:, g, c, t], clip=True)
            values.append(100 * mean); lows.append(100 * lo); highs.append(100 * hi)
        ax.bar(x, values, color=[BLUE, TEAL, BLUE, TEAL], width=0.62, zorder=3)
        ax.errorbar(
            x, values,
            yerr=[[v - lo for v, lo in zip(values, lows)],
                  [hi - v for v, hi in zip(values, highs)]],
            fmt="none", ecolor=INK, capsize=4, zorder=4,
        )
        for xi, value in zip(x, values):
            ax.text(xi, min(103, value + 2), f"{value:.1f}%", ha="center", fontweight="bold")
        ax.set_xticks(x); ax.set_xticklabels([arm_short(g, c) for g, c in cells], fontsize=9)
        ax.set_title(f"Test {'ON' if t else 'OFF'}", fontweight="bold")
        ax.set_ylim(70, 105); ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("Detector metric resolved (%)")
    fig.suptitle("Triggering-metric resolution by factorial arm", fontweight="bold", fontsize=14)
    fig.text(
        0.5, 0.01,
        "Sol replacement for the old metric-magnitude figure; exact after-metric magnitudes were not persisted for all 456 repairs",
        ha="center", color=MUTED, fontsize=8.8,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    save(fig, out_dir, "fig8_detector_resolution_by_arm")


def fig6(attempts, out_dir):
    order = ["strict_success", "private_regression", "metric_unresolved", "build_failed"]
    colors = {
        "strict_success": TEAL,
        "private_regression": RED,
        "metric_unresolved": AMBER,
        "build_failed": LGRAY,
    }
    groups = []
    for g in (0, 1):
        rows = [row for row in attempts if int(row["grounding_enabled"]) == g]
        groups.append(Counter(gate_category(row) for row in rows))

    fig, ax = plt.subplots(figsize=(8.0, 3.7), dpi=300)
    for i, counts in enumerate(groups):
        left = 0.0
        for category in order:
            count = counts[category]
            percent = 100 * count / 228
            ax.barh(i, percent, left=left, color=colors[category],
                    height=0.62, zorder=3)
            if percent >= 3:
                ax.text(
                    left + percent / 2, i, str(count),
                    ha="center", va="center", fontsize=9,
                    color="white" if category in {"strict_success", "private_regression"} else INK,
                    fontweight="bold",
                )
            left += percent
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["Ungrounded", "Grounded"])
    ax.invert_yaxis()
    ax.set_xlim(0, 100)
    ax.set_xlabel("Share of final repairs (%) · n=228 per grounding level")
    ax.set_title("Strict-success outcome ladder by binary grounding assignment",
                 fontweight="bold")
    ax.legend(
        handles=[Patch(color=colors[key], label=key.replace("_", " ")) for key in order],
        ncol=4, frameon=False, loc="upper center",
        bbox_to_anchor=(0.5, -0.22), fontsize=8.7,
    )
    ax.grid(axis="y", visible=False)
    fig.tight_layout(rect=(0, 0.11, 1, 1))
    save(fig, out_dir, "fig6_ladder_by_grounding")
    for extension in ("png", "svg", "pdf"):
        shutil.copy2(
            out_dir / f"fig6_ladder_by_grounding.{extension}",
            out_dir / f"fig6_ladder_by_context.{extension}",
        )


def fig9(attempts, out_dir, tables_dir):
    arms = [(g, c, t) for c in (0, 1) for g in (0, 1) for t in (0, 1)]
    metrics = [
        ("metric_resolved", "Detector metric resolved", BLUE, "s"),
        ("private_test_passed", "Private behavior preserved", PURPLE, "^"),
        ("strict_success", "Strict success", TEAL, "o"),
    ]
    table_rows = []
    fig, ax = plt.subplots(figsize=(10.2, 6.1), dpi=300)
    offsets = [-0.18, 0.0, 0.18]
    for i, arm in enumerate(arms):
        g, c, t = arm
        rows = [
            row for row in attempts
            if int(row["grounding_enabled"]) == g
            and control_index(row["control_structure"]) == c
            and int(row["visible_tests_enabled"]) == t
        ]
        table_row = {
            "grounding": g,
            "iterative": c,
            "visible_test": t,
            "attempts": len(rows),
            "build_passed_pct": 100 * np.mean([row["build_passed"] for row in rows]),
        }
        for offset, (field, label, color, marker) in zip(offsets, metrics):
            value = 100 * np.mean([row[field] for row in rows])
            table_row[f"{field}_pct"] = value
            ax.plot(value, i + offset, marker=marker, color=color, ms=7.5,
                    linestyle="none", label=label if i == 0 else None, zorder=4)
        table_rows.append(table_row)
    with (tables_dir / "sol_repair_outcome_profile.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table_rows[0]))
        writer.writeheader()
        writer.writerows(table_rows)

    ax.set_yticks(range(len(arms)))
    ax.set_yticklabels([arm_label(*arm) for arm in arms], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(72, 101)
    ax.set_xlabel("Repairs satisfying outcome (%) · n=57 per arm")
    ax.set_title("Repair outcome profile by factorial arm", fontweight="bold")
    ax.legend(frameon=False, ncol=3, loc="upper center",
              bbox_to_anchor=(0.5, -0.12), fontsize=9)
    ax.grid(axis="y", visible=False)
    fig.text(
        0.5, 0.01,
        "All arms achieved 100% final-build success; whole-solution quality deltas were not persisted",
        ha="center", color=MUTED, fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    save(fig, out_dir, "fig9_repair_outcome_profile")
    for extension in ("png", "svg", "pdf"):
        shutil.copy2(
            out_dir / f"fig9_repair_outcome_profile.{extension}",
            out_dir / f"fig9_quality_impact.{extension}",
        )


def fig10(attempts, out_dir):
    arms = [(g, c, t) for c in (0, 1) for g in (0, 1) for t in (0, 1)]
    fig, ax = plt.subplots(figsize=(10.0, 5.8), dpi=300)
    for i, arm in enumerate(arms):
        g, c, t = arm
        rows = [
            row for row in attempts
            if int(row["grounding_enabled"]) == g
            and control_index(row["control_structure"]) == c
            and int(row["visible_tests_enabled"]) == t
        ]
        preserved = sum(row["private_test_passed"] for row in rows)
        regressions = 57 - preserved
        ax.barh(i, preserved, color=TEAL, height=0.66, zorder=3)
        if regressions:
            ax.barh(i, regressions, left=preserved, color=RED, height=0.66, zorder=3)
            ax.text(preserved + regressions / 2, i, str(regressions), ha="center", va="center",
                    color="white", fontweight="bold")
        ax.text(preserved / 2, i, str(preserved), ha="center", va="center",
                color="white", fontweight="bold")
    ax.set_yticks(range(len(arms)))
    ax.set_yticklabels([arm_label(*arm) for arm in arms], fontsize=9)
    ax.invert_yaxis(); ax.set_xlim(0, 57)
    ax.set_xlabel("Final repairs evaluated by private Layer 3 · n=57 per arm")
    ax.set_title("Private behavioral preservation by factorial arm", fontweight="bold")
    ax.legend(
        handles=[Patch(color=TEAL, label="behavior preserved"),
                 Patch(color=RED, label="behavioral regression")],
        frameon=False, ncol=2, loc="upper center", bbox_to_anchor=(0.5, -0.11),
    )
    ax.grid(axis="y", visible=False)
    fig.text(0.5, 0.01, "All nine regressions came from one target: VatResolver.Resolve",
             ha="center", color=MUTED, fontsize=9)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    save(fig, out_dir, "fig10_layer3_behaviour")


def write_tables(attempts, out_dir):
    rows = []
    for c in (0, 1):
        for g in (0, 1):
            for t in (0, 1):
                group = [
                    row for row in attempts
                    if int(row["grounding_enabled"]) == g
                    and control_index(row["control_structure"]) == c
                    and int(row["visible_tests_enabled"]) == t
                ]
                rows.append({
                    "grounding": g,
                    "iterative": c,
                    "visible_test": t,
                    "attempts": len(group),
                    "build_passed": sum(row["build_passed"] for row in group),
                    "metric_resolved": sum(row["metric_resolved"] for row in group),
                    "private_passed": sum(row["private_test_passed"] for row in group),
                    "strict_success": sum(row["strict_success"] for row in group),
                    "mean_total_tokens": np.mean([row["total_tokens"] for row in group]),
                })
    with (out_dir / "sol_factorial_figure_data.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts", required=True, type=Path)
    parser.add_argument("--traces", required=True, type=Path)
    parser.add_argument("--metric-trace", required=True, type=Path)
    parser.add_argument("--effect-figure-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--tables-dir", required=True, type=Path)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.tables_dir.mkdir(parents=True, exist_ok=True)

    attempts = json.loads(args.attempts.read_text(encoding="utf-8-sig"))
    if len(attempts) != 456:
        raise ValueError("expected 456 attempts")
    records = load_final_records(args.traces)
    _instances, strict_cube = build_cube(attempts, "strict_success")
    _instances, metric_cube = build_cube(attempts, "metric_resolved")

    fig1(strict_cube, args.out_dir)
    fig2(strict_cube, args.out_dir)
    fig3(attempts, args.out_dir)
    fig4(strict_cube, args.out_dir, args.tables_dir)
    fig5(records, args.out_dir, args.tables_dir)
    fig6(attempts, args.out_dir)
    fig7(args.metric_trace, args.out_dir)
    fig8(metric_cube, args.out_dir)
    fig9(attempts, args.out_dir, args.tables_dir)
    fig10(attempts, args.out_dir)
    write_tables(attempts, args.tables_dir)

    for extension in ("png", "svg", "pdf"):
        shutil.copy2(
            args.effect_figure_dir / f"factorial_visible_test_effect.{extension}",
            args.out_dir / f"fig11_visible_test_effect.{extension}",
        )
    print("copied fig11_visible_test_effect.png/.svg/.pdf")


if __name__ == "__main__":
    main()
