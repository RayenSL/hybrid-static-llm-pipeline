#!/usr/bin/env python3
"""Layer-3 behavioural-preservation figure: stacked bars (preserved vs behavioural regression) per
anti-pattern, split by arm. Reads output/tables/layer3_behaviour_preservation.csv. Saves PNG + SVG + PDF.
"""
from __future__ import annotations
import argparse, csv, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

INK  = "#1a1a1a"
GOOD = "#1a7f37"   # behaviour preserved
BAD  = "#cf222e"   # behavioural regression

TYPE_ORDER = ["long_method", "god_class", "obsolete_api_usage"]
TYPE_LABEL = {"long_method": "Long Method", "god_class": "God Class", "obsolete_api_usage": "Obsolete API"}
ORACLE     = {"long_method": "golden-master", "god_class": "golden-master", "obsolete_api_usage": "smoke"}
ARM_ORDER  = ["agentic", "grounded_iterative"]
ARM_SHORT  = {"agentic": "Agentic", "grounded_iterative": "Grounded"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path("output/tables/layer3_behaviour_preservation.csv"))
    ap.add_argument("--out-dir", type=Path, default=Path("output/figures"))
    ap.add_argument("--name", type=str, default="fig10_layer3_behaviour")
    args = ap.parse_args(argv)

    data = {}
    for r in csv.DictReader(open(args.csv, encoding="utf-8-sig")):
        data[(r["arm"], r["anti_pattern"])] = (int(r["preserved"]), int(r["regression"]), int(r["n"]))

    fig, ax = plt.subplots(figsize=(9.0, 5.2), dpi=300)
    bw = 0.38
    xt, xl = [], []
    for gi, typ in enumerate(TYPE_ORDER):
        for ai, arm in enumerate(ARM_ORDER):
            pres, reg, n = data.get((arm, typ), (0, 0, 0))
            x = gi + (ai - 0.5) * (bw + 0.02)
            ax.bar(x, pres, bw, color=GOOD, edgecolor="white", zorder=3)
            if reg:
                ax.bar(x, reg, bw, bottom=pres, color=BAD, edgecolor="white", zorder=3)
                ax.annotate(str(reg), (x, pres + reg), textcoords="offset points", xytext=(0, 3),
                            ha="center", fontsize=9, fontweight="bold", color=BAD)
            ax.annotate(str(pres), (x, pres / 2), ha="center", va="center", fontsize=9,
                        color="white", fontweight="bold")
            ax.annotate(ARM_SHORT[arm], (x, -0.6), ha="center", va="top", fontsize=8.3,
                        color="#444", annotation_clip=False)
            xt.append(x); xl.append("")
        ax.annotate(f"{TYPE_LABEL[typ]}\n({ORACLE[typ]})", (gi, -3.0), ha="center", va="top",
                    fontsize=10, color=INK, annotation_clip=False)

    ax.set_ylim(0, 33)
    ax.set_xlim(-0.7, len(TYPE_ORDER) - 0.3)
    ax.set_xticks([])
    ax.set_ylabel("Built repairs", fontsize=11, color=INK)
    ax.set_title("Layer 3: behavioural preservation of applied repairs", fontsize=13,
                 fontweight="bold", color=INK, pad=10)
    ax.legend(handles=[Patch(facecolor=GOOD, label="behaviour preserved"),
                       Patch(facecolor=BAD,  label="behavioural regression")],
              loc="lower center", ncol=2, fontsize=9.5, frameon=False, bbox_to_anchor=(0.5, -0.28))
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)

    fig.subplots_adjust(bottom=0.24)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "svg", "pdf"):
        fig.savefig(args.out_dir / f"{args.name}.{ext}", dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"wrote {args.out_dir / (args.name + '.png')} (+ .svg, .pdf)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
