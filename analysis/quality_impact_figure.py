#!/usr/bin/env python3
"""Whole-solution quality impact per repair, by architecture (Table 5.16 as a figure).
Diverging grouped bars: per-repair mean change on each instrument. Below zero = the repair
removed problems (improvement); above zero = it added them. Saves PNG + SVG + PDF.

Usage: python analysis/quality_impact_figure.py [--csv output/tables/quality_impact_by_architecture.csv]
"""
from __future__ import annotations
import argparse, csv, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

INK = "#1a1a1a"
GOOD = "#1a7f37"   # improvement band (below zero)
BAD  = "#cf222e"   # worsening band (above zero)
BARS = {
    "smell_delta_mean":        ("Smell (Layer 1, detector)",   "#1f5fbf"),
    "ca_headline_delta_mean":  ("CA headline (Layer 2)",       "#d1651d"),
    "ca_all_delta_mean":       ("CA all-rules (Layer 2)",      "#2a9d8f"),
}
ARM_ORDER = ["hybrid", "agentic", "grounded_iterative"]
ARM_LABEL = {"hybrid": "Hybrid (Minimal)", "agentic": "Agentic", "grounded_iterative": "Grounded-iterative"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path("output/tables/quality_impact_by_architecture.csv"))
    ap.add_argument("--out-dir", type=Path, default=Path("output/figures"))
    ap.add_argument("--name", type=str, default="fig9_quality_impact")
    args = ap.parse_args(argv)

    rows = {r["architecture"]: r for r in csv.DictReader(open(args.csv, encoding="utf-8-sig"))}
    arms = [a for a in ARM_ORDER if a in rows]

    fig, ax = plt.subplots(figsize=(8.6, 5.0), dpi=300)
    n_ins = len(BARS)
    group_w = 0.8
    bar_w = group_w / n_ins

    lo = min(float(rows[a][k]) for a in arms for k in BARS)
    hi = max(float(rows[a][k]) for a in arms for k in BARS)
    top, bot = max(hi, 0) + 0.25, min(lo, 0) - 0.25

    # direction bands
    ax.axhspan(bot, 0, color=GOOD, alpha=0.06, zorder=0)
    ax.axhspan(0, top, color=BAD, alpha=0.06, zorder=0)
    ax.axhline(0, color=INK, lw=1.2, zorder=3)
    ax.text(len(arms) - 0.5, bot + 0.02, "below 0 = fewer problems after repair (improvement)",
            ha="right", va="bottom", fontsize=8, color=GOOD, style="italic")

    for gi, arm in enumerate(arms):
        for bi, (key, (label, col)) in enumerate(BARS.items()):
            x = gi + (bi - (n_ins - 1) / 2) * bar_w
            v = float(rows[arm][key])
            ax.bar(x, v, bar_w * 0.92, color=col, edgecolor="white", linewidth=0.6, zorder=4,
                   label=label if gi == 0 else None)
            ax.annotate(f"{v:+.2f}", (x, v), textcoords="offset points",
                        xytext=(0, 3 if v >= 0 else -11), ha="center", fontsize=7.5, color=INK)

    ax.set_xticks(range(len(arms)))
    ax.set_xticklabels(
        [f"{ARM_LABEL[a]}\n$n$={rows[a]['n_built']}, collateral {float(rows[a]['collateral_pct']):.1f}%" for a in arms],
        fontsize=9.5)
    ax.set_ylim(bot, top)
    ax.set_ylabel("Mean change per repair (count)", fontsize=11, color=INK)
    ax.set_title("Whole-solution quality impact of applied repairs", fontsize=12.5,
                 fontweight="bold", color=INK, pad=10)
    ax.legend(loc="upper left", fontsize=8.6, framealpha=0.95)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)

    fig.tight_layout()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(args.out_dir / f"{args.name}.{ext}", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {args.out_dir / (args.name + '.png')} (+ .svg, .pdf)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
