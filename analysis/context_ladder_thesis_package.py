#!/usr/bin/env python3
"""Build thesis-ready figures and source data for the 2026-08 context-ladder reruns."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch


INK = "#1a1a1a"
BODY = "#30363b"
MUTED = "#66707a"
GRID = "#d9dee2"
TEAL = "#2a8580"
PURPLE = "#6f4c9b"
BLUE = "#3977a8"
AMBER = "#d99000"
RED = "#cf4b45"
LIGHT = "#c9ced3"
PANEL = "#f5f8fc"
CREAM = "#fffaf3"

LEVELS = ["minimal", "structural", "relational", "full"]

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10.5,
    "axes.edgecolor": MUTED,
    "axes.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "svg.fonttype": "none",
})


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return centre - half, centre + half


def save(fig, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg", "pdf"):
        fig.savefig(out_dir / f"{name}.{extension}", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def load_levels(path: Path, expected_observations: int, expected_n: int) -> tuple[dict, list[dict]]:
    summary = json.loads(path.read_text(encoding="utf-8-sig"))
    if summary["observations"] != expected_observations:
        raise ValueError(f"{path}: expected {expected_observations} observations")
    by_level = {row["level"]: row for row in summary["levels"]}
    if list(level for level in LEVELS if level not in by_level):
        raise ValueError(f"{path}: missing context level")
    rows = [by_level[level] for level in LEVELS]
    if any(row["n"] != expected_n for row in rows):
        raise ValueError(f"{path}: unexpected level denominator")
    return summary, rows


def corpus_source_rows(levels: list[dict]) -> list[dict]:
    result = []
    for row in levels:
        n = row["n"]
        verified = row["resolved"]
        preserved = row["detector_resolved_and_layer3_pass"]
        v_lo, v_hi = wilson(verified, n)
        p_lo, p_hi = wilson(preserved, n)
        result.append({
            "context": row["level"], "assigned_n": n,
            "verified_n": verified, "verified_pct": 100 * verified / n,
            "verified_ci95_lo_pct": 100 * v_lo, "verified_ci95_hi_pct": 100 * v_hi,
            "behaviour_preserving_verified_n": preserved,
            "behaviour_preserving_verified_pct": 100 * preserved / n,
            "behaviour_preserving_ci95_lo_pct": 100 * p_lo,
            "behaviour_preserving_ci95_hi_pct": 100 * p_hi,
        })
    return result


def industrial_source_rows(levels: list[dict]) -> list[dict]:
    result = []
    for row in levels:
        n = row["n"]
        result.append({
            "context": row["level"], "assigned_n": n,
            "detector_resolved_n": row["resolved"],
            "behaviour_preserved_n": row["oracle_behaviour_preserved"],
            "behavioural_change_n": row["oracle_behavioural_change"],
            "production_build_failed_n": row["oracle_production_build_failed"],
            "cross_file_truncated_n": row["cross_file_truncated_n"],
            "nominal_cost_usd": row["nominal_cost_usd_sum"],
        })
    return result


def figure_corpus(rows: list[dict], out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.7, 5.35), dpi=300)
    y = list(range(4))
    height = 0.27
    series = [
        ("verified_pct", "verified_ci95_lo_pct", "verified_ci95_hi_pct", TEAL,
         "Build + detector resolved"),
        ("behaviour_preserving_verified_pct", "behaviour_preserving_ci95_lo_pct",
         "behaviour_preserving_ci95_hi_pct", PURPLE,
         "Build + detector resolved + private oracle passed"),
    ]
    for offset, (value_key, lo_key, hi_key, color, label) in zip((-height / 1.7, height / 1.7), series):
        values = [row[value_key] for row in rows]
        lows = [row[lo_key] for row in rows]
        highs = [row[hi_key] for row in rows]
        positions = [value + offset for value in y]
        ax.barh(positions, values, height=height, color=color, label=label, zorder=3)
        ax.errorbar(values, positions,
                    xerr=[[max(0.0, v - lo) for v, lo in zip(values, lows)],
                          [max(0.0, hi - v) for v, hi in zip(values, highs)]],
                    fmt="none", ecolor=INK, capsize=3.5, lw=1.1, zorder=4)
        for value, position, row in zip(values, positions, rows):
            count_key = "verified_n" if value_key == "verified_pct" else "behaviour_preserving_verified_n"
            high = row[hi_key]
            x = value - 1.1 if value > 94 else high + 0.7
            align = "right" if value > 94 else "left"
            colour = "white" if value > 94 else INK
            ax.text(x, position, f"{row[count_key]}/{row['assigned_n']} ({value:.1f}%)",
                    va="center", ha=align, fontsize=9, fontweight="bold", color=colour, zorder=5)
    ax.set_yticks(y)
    ax.set_yticklabels([row["context"].title() for row in rows], fontweight="bold")
    ax.invert_yaxis()
    ax.set_xlim(55, 105)
    ax.set_xlabel("Share of assigned repairs (%) - n = 108 per level")
    ax.set_title("Context-ladder outcomes on the constructed corpus", fontweight="bold", fontsize=14, pad=12)
    ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.27), ncol=2, fontsize=9)
    ax.grid(axis="y", visible=False)
    fig.text(0.5, 0.012,
             "Error bars are descriptive 95% Wilson intervals; inference uses 108 matched target-repetition blocks.",
             ha="center", color=MUTED, fontsize=9)
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    save(fig, out_dir, "figure_context_ladder_corpus")


def figure_industrial(rows: list[dict], out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.3, 5.15), dpi=300)
    y = list(range(4))
    categories = [
        ("behaviour_preserved_n", "Behaviour preserved", TEAL),
        ("behavioural_change_n", "Behavioural change", RED),
        ("production_build_failed_n", "Production build failed", LIGHT),
    ]
    left = [0.0] * 4
    for key, label, color in categories:
        values = [100 * row[key] / row["assigned_n"] for row in rows]
        ax.barh(y, values, left=left, color=color, height=0.64, label=label, zorder=3)
        for index, (start, width, row) in enumerate(zip(left, values, rows)):
            count = row[key]
            if count:
                ax.text(start + width / 2, index, str(count), ha="center", va="center",
                        fontweight="bold", fontsize=9,
                        color="white" if key != "production_build_failed_n" else INK, zorder=4)
        left = [start + width for start, width in zip(left, values)]
    for index, row in enumerate(rows):
        ax.text(101.2, index, f"resolved {row['detector_resolved_n']}/27", va="center",
                ha="left", fontsize=9, color=BODY)
    ax.set_yticks(y)
    ax.set_yticklabels([row["context"].title() for row in rows], fontweight="bold")
    ax.invert_yaxis()
    ax.set_xlim(0, 116)
    ax.set_xlabel("Share of assigned repairs (%) - n = 27 per level")
    ax.set_title("Context-ladder outcomes on Ibis.Besteksadministratie", fontweight="bold", fontsize=14, pad=12)
    ax.legend(frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.25), ncol=3, fontsize=9)
    ax.grid(axis="y", visible=False)
    fig.text(0.5, 0.012,
             "Descriptive ecological-validity probe: 9 targets x 3 repetitions; no hypothesis test or pooled corpus estimate.",
             ha="center", color=MUTED, fontsize=9)
    fig.tight_layout(rect=(0, 0.10, 1, 1))
    save(fig, out_dir, "figure_context_ladder_industrial")


def figure_design(out_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(12.3, 5.5), dpi=300)
    ax.set_xlim(0, 12.3)
    ax.set_ylim(0, 5.5)
    ax.axis("off")

    def box(x, y, w, h, title, body, fill, *, body_size=7.6):
        patch = FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.025,rounding_size=0.08",
                               facecolor=fill, edgecolor=MUTED, linewidth=1.0)
        ax.add_patch(patch)
        ax.text(x + w / 2, y + h - 0.18, title, ha="center", va="top", fontweight="bold", fontsize=9.4)
        ax.text(x + w / 2, y + h - 0.62, body, ha="center", va="top", fontsize=body_size,
                color=BODY, linespacing=1.35)
        return x, y, w, h

    def arrow(a, b):
        ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=12,
                                     color=MUTED, linewidth=1.15))

    ladder = box(0.28, 1.22, 2.48, 3.65, "Shared ladder-v2.0.0",
                 "Minimal\ncode fragment\n\nStructural\n+ diagnosis, metrics, thresholds\n\nRelational\n+ enclosing declaration + window\n\nFull\n+ referenced declarations\n(cap: 8 files / 60,000 chars)", "#dfe7f4")
    corpus = box(3.20, 3.08, 2.82, 1.78, "Constructed corpus",
                 "36 targets x 4 levels x 3 repetitions\n432 direct-editing assignments\n13 God Class - 13 Long Method\n10 Obsolete API Usage", PANEL, body_size=7.3)
    industry = box(3.20, 0.72, 2.82, 1.78, "Industrial repository",
                   "9 targets x 4 levels x 3 repetitions\n108 direct-editing assignments\n8 admitted Long Method - 1 God Class\nDescriptive; no hypothesis test", CREAM, body_size=7.2)
    repair = box(6.68, 1.57, 2.55, 2.54, "One evaluated model call",
                 "gpt-5.6-sol edits the complete file\nSingle-shot - no applier\nVisible generated tests OFF\nPristine isolated working copy\nNo retries", "#fde7cf", body_size=7.5)
    verify = box(9.82, 1.57, 2.20, 2.54, "Sealed measurement",
                 "Production build gate\nTriggering-detector\nremeasurement\nHidden author-written oracle\nWhole-solution quality scan\nTokens, cost, and truncation", "#dff1e5", body_size=7.2)
    arrow((ladder[0] + ladder[2], 3.7), (corpus[0], 3.7))
    arrow((ladder[0] + ladder[2], 1.65), (industry[0], 1.65))
    arrow((corpus[0] + corpus[2], 3.7), (repair[0], 3.25))
    arrow((industry[0] + industry[2], 1.65), (repair[0], 2.35))
    arrow((repair[0] + repair[2], 2.84), (verify[0], 2.84))
    ax.text(6.15, 5.24, "Context-ladder rerun design", ha="center", va="center",
            fontsize=15, fontweight="bold", color=INK)
    ax.text(6.15, 0.28, "The populations share the ladder definition and measurement logic, but their denominators are never pooled.",
            ha="center", va="center", fontsize=9.2, color=MUTED)
    save(fig, out_dir, "figure_context_ladder_design")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-summary", type=Path, required=True)
    parser.add_argument("--industrial-summary", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    corpus_summary, corpus_levels = load_levels(args.corpus_summary, 432, 108)
    industrial_summary, industrial_levels = load_levels(args.industrial_summary, 108, 27)
    corpus_rows = corpus_source_rows(corpus_levels)
    industrial_rows = industrial_source_rows(industrial_levels)
    write_csv(args.out_dir / "figure_context_ladder_corpus.csv", corpus_rows)
    write_csv(args.out_dir / "figure_context_ladder_industrial.csv", industrial_rows)
    figure_design(args.out_dir)
    figure_corpus(corpus_rows, args.out_dir)
    figure_industrial(industrial_rows, args.out_dir)

    manifest = {
        "corpus_observations": corpus_summary["observations"],
        "industrial_observations": industrial_summary["observations"],
        "corpus_cochran_q": corpus_summary["cochran_q"],
        "corpus_adjacent_contrasts": corpus_summary["adjacent_contrasts"],
        "industrial_inference": "descriptive_only_no_hypothesis_test",
        "outputs": sorted(path.name for path in args.out_dir.iterdir()),
    }
    (args.out_dir / "FIGURE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote thesis context-ladder package to {args.out_dir}")


if __name__ == "__main__":
    main()
