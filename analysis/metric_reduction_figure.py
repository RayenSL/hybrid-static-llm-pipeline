#!/usr/bin/env python3
"""Aggregate before→after triggering-metric reduction across ALL resolved repairs of the iterative
arms, from metric-aggregate JSON(s). One slopegraph panel per anti-pattern type: Long Method (CC),
God Class (WMC), Obsolete API (binary present→absent). Saves a thesis-ready PNG + SVG.

Usage:
    python analysis/metric_reduction_figure.py agg1.json [agg2.json ...] [--out-dir output/figures] [--name fig8_metric_reduction]
"""
from __future__ import annotations
import argparse, json, statistics as st, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

INK    = "#1a1a1a"
THRESH = "#cf222e"
ARM = {"agentic": "#d1651d", "grounded_iterative": "#1f5fbf"}
ARM_LABEL = {"agentic": "agentic (ungrounded)", "grounded_iterative": "grounded-iterative"}

PANELS = [
    ("long_method",       "Long Method", "Cyclomatic complexity (CC)", 10),
    ("god_class",         "God Class",   "Weighted methods / class (WMC)", 47),
    ("obsolete_api_usage", "Obsolete API", "Obsolete API usage", None),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--out-dir", type=Path, default=Path("output/figures"))
    ap.add_argument("--name", type=str, default="fig8_metric_reduction")
    args = ap.parse_args(argv)

    rows = []
    for p in args.inputs:
        rows += json.loads(p.read_text(encoding="utf-8-sig"))

    # Dedup to one point per (arm, type, symbol): before is constant, after = mean over resolved runs.
    agg: dict[tuple, dict] = {}
    for r in rows:
        k = (r["architecture"], r["anti_pattern_type"], r["symbol"])
        agg.setdefault(k, {"before": r["before"], "after": []})["after"].append(r["after"])
    inst = [{"arm": a, "type": t, "symbol": s, "before": v["before"], "after": st.mean(v["after"])}
            for (a, t, s), v in agg.items()]

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 5.2), dpi=300)

    for ax, (typ, title, ylab, thr) in zip(axes, PANELS):
        sub = [d for d in inst if d["type"] == typ]
        binary = thr is None

        if binary:
            ax.set_ylim(-0.25, 1.25)
            ax.set_yticks([0, 1]); ax.set_yticklabels(["absent\n(resolved)", "present"])
        else:
            top = max([d["before"] for d in sub] + [thr]) * 1.12
            ax.set_ylim(0, top)
            ax.axhspan(thr, top, color=THRESH, alpha=0.07, zorder=0)
            ax.axhline(thr, color=THRESH, ls="--", lw=1.3, zorder=1)
            ax.text(0.5, thr, f" threshold ({thr})", color=THRESH, fontsize=8, va="bottom", ha="center")

        # individual repair slopes (arm-coloured, translucent)
        for d in sub:
            ax.plot([0, 1], [d["before"], d["after"]], color=ARM[d["arm"]], lw=1.1, alpha=0.35, zorder=2)
            ax.plot([0, 1], [d["before"], d["after"]], color=ARM[d["arm"]], lw=0, marker="o", ms=4,
                    mfc=ARM[d["arm"]], mec="white", mew=0.5, alpha=0.65, zorder=3)

        # per-arm mean slope (bold)
        note = []
        for arm in ("agentic", "grounded_iterative"):
            a = [d for d in sub if d["arm"] == arm]
            if not a: continue
            mb, ma = st.mean(d["before"] for d in a), st.mean(d["after"] for d in a)
            ax.plot([0, 1], [mb, ma], color=ARM[arm], lw=3.0, marker="o", ms=9,
                    mfc=ARM[arm], mec="white", mew=1.6, zorder=5)
            if not binary:
                below = sum(1 for d in a if d["after"] < thr)
                note.append(f"{ARM_LABEL[arm].split()[0]}: {mb:.1f}→{ma:.1f} ({below}/{len(a)}✓)")
            else:
                note.append(f"{ARM_LABEL[arm].split()[0]}: {len(a)} resolved")

        ax.set_title(f"{title}", fontsize=12, fontweight="bold", color=INK, pad=18)
        ax.set_ylabel(ylab, fontsize=10.5, color=INK)
        ax.set_xticks([0, 1]); ax.set_xticklabels(["before", "after"], fontsize=10.5)
        ax.set_xlim(-0.25, 1.25)
        ax.text(0.5, 1.015, "  |  ".join(note), transform=ax.transAxes, ha="center", va="bottom",
                fontsize=8.2, color="#444")
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)

    handles = [Line2D([0], [0], color=ARM[a], lw=3, marker="o", mfc=ARM[a], mec="white", label=ARM_LABEL[a])
               for a in ("agentic", "grounded_iterative")]
    handles.append(Line2D([0], [0], color="#999", lw=1.1, alpha=0.5, label="individual repair"))
    fig.legend(handles=handles, loc="lower center", ncol=3, fontsize=9, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Triggering-metric reduction across all resolved repairs (iterative arms)",
                 fontsize=13.5, fontweight="bold", color=INK, y=1.02)

    fig.tight_layout(rect=(0, 0.04, 1, 1))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(args.out_dir / f"{args.name}.{ext}", bbox_inches="tight", facecolor="white", dpi=300)
    plt.close(fig)
    print(f"wrote {args.out_dir / (args.name + '.png')} (+ .svg)  [{len(inst)} instance-arm points]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
