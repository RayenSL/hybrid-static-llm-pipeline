#!/usr/bin/env python3
"""Render a single run's per-iteration triggering-metric trajectory (the supervisor's
"do the metrics improve iteration by iteration?" question) from a metric-trace JSON
produced by `hybridlens metric-trace`. Saves a thesis-ready PNG + SVG.

Usage:
    python analysis/metric_trajectory_figure.py <trace.json> [--out-dir output/figures] [--name fig7_metric_trajectory]
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

INK      = "#1a1a1a"
CC_COL   = "#1f5fbf"   # cyclomatic complexity (primary)
LOC_COL  = "#8a8f98"   # lines of code (secondary, muted)
OK_COL   = "#1a7f37"   # build passed
FAIL_COL = "#cf222e"   # build failed
THRESH   = "#cf222e"   # threshold line / trigger band


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("trace", type=Path, help="metric-trace JSON")
    ap.add_argument("--out-dir", type=Path, default=Path("output/figures"))
    ap.add_argument("--name", type=str, default=None)
    args = ap.parse_args(argv)

    d = json.loads(args.trace.read_text(encoding="utf-8-sig"))
    series = d["series"]
    xs   = [r["iteration"] for r in series]
    cc   = [r["cc"] for r in series]
    loc  = [r["loc"] for r in series]
    oks  = [r["build_ok"] for r in series]
    cc_thr  = d.get("cc_threshold", 10)
    arch    = (d.get("architecture") or "agentic").replace("_", "-")
    target  = d.get("target_method") or d.get("symbol") or "target method"

    labels = []
    for r in series:
        ph = r["phase"]
        ph = "Original" if ph == "original" else ph.replace("edit ", "Edit ")
        labels.append(f"{ph}\n{'build ✓' if r['build_ok'] else 'build ✗'}")

    fig, axL = plt.subplots(figsize=(8.4, 5.0), dpi=300)
    axR = axL.twinx()

    # Trigger band (Long Method fires when CC > threshold).
    top = max(max(cc), cc_thr) + 2
    axL.axhspan(cc_thr, top, color=THRESH, alpha=0.07, zorder=0)
    axL.axhline(cc_thr, color=THRESH, ls="--", lw=1.3, zorder=1)
    axL.text(xs[0] - 0.30, cc_thr + 0.15, f"Long Method threshold (CC > {cc_thr})",
             color=THRESH, fontsize=8.5, va="bottom", ha="left")

    # LOC (secondary, muted) behind CC.
    axR.plot(xs, loc, color=LOC_COL, lw=1.6, ls=(0, (4, 2)), marker="s", ms=5,
             mfc="white", mec=LOC_COL, zorder=2, label="Lines of code")

    # CC (primary), markers coloured by build outcome.
    axL.plot(xs, cc, color=CC_COL, lw=2.4, zorder=3)
    for x, y, ok in zip(xs, cc, oks):
        axL.plot(x, y, marker="o", ms=12, zorder=4,
                 mfc=(OK_COL if ok else FAIL_COL), mec="white", mew=1.6)
        axL.annotate(str(y), (x, y), textcoords="offset points", xytext=(0, 14),
                     ha="center", fontsize=11, fontweight="bold", color=CC_COL)

    # Narrative annotations.
    axL.annotate("detected\nCC 11 (> 10)", (xs[0], cc[0]), textcoords="offset points",
                 xytext=(6, -34), fontsize=8.6, color=INK,
                 arrowprops=dict(arrowstyle="-", color="#bbb", lw=0.8))
    if len(xs) >= 2:
        axL.annotate("metric resolved (CC 6)\nbut build fails", (xs[1], cc[1]),
                     textcoords="offset points", xytext=(-6, -46), ha="center",
                     fontsize=8.6, color=FAIL_COL,
                     arrowprops=dict(arrowstyle="-", color="#bbb", lw=0.8))
    if len(xs) >= 3:
        axL.annotate("compiler feedback →\nbuilds ✓, metric held", (xs[2], cc[2]),
                     textcoords="offset points", xytext=(-14, 30), ha="center",
                     fontsize=8.6, color=OK_COL,
                     arrowprops=dict(arrowstyle="-", color="#bbb", lw=0.8))

    axL.set_xticks(xs)
    axL.set_xticklabels(labels, fontsize=9.5)
    axL.set_xlim(-0.35, xs[-1] + 0.35)
    axL.set_ylim(0, top)
    axL.set_ylabel("Cyclomatic complexity (CC)", color=CC_COL, fontsize=11)
    axL.tick_params(axis="y", labelcolor=CC_COL)
    axR.set_ylabel("Lines of code (LOC)", color=LOC_COL, fontsize=11)
    axR.tick_params(axis="y", labelcolor=LOC_COL)
    axR.set_ylim(0, max(loc) + 15)

    axL.set_title(f"Metric trajectory per iteration — {arch}\n{target} (Long Method)",
                  fontsize=12.5, fontweight="bold", color=INK, pad=12)

    legend = [
        Line2D([0], [0], color=CC_COL, lw=2.4, marker="o", mfc="white", mec=CC_COL, label="Cyclomatic complexity"),
        Line2D([0], [0], color=LOC_COL, lw=1.6, ls=(0, (4, 2)), marker="s", mfc="white", mec=LOC_COL, label="Lines of code"),
        Line2D([0], [0], marker="o", ms=10, lw=0, mfc=OK_COL, mec="white", label="build passed"),
        Line2D([0], [0], marker="o", ms=10, lw=0, mfc=FAIL_COL, mec="white", label="build failed"),
        Patch(facecolor=THRESH, alpha=0.12, label=f"triggers (CC > {cc_thr})"),
    ]
    axL.legend(handles=legend, loc="upper right", fontsize=8.4, framealpha=0.95, ncol=1)
    for sp in ("top",):
        axL.spines[sp].set_visible(False); axR.spines[sp].set_visible(False)

    fig.tight_layout()
    name = args.name or f"fig_metric_trajectory_{Path(d.get('file','run')).stem}"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(args.out_dir / f"{name}.{ext}", bbox_inches="tight",
                    facecolor="white", dpi=300)
    plt.close(fig)
    print(f"wrote {args.out_dir / (name + '.png')} (+ .svg)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
