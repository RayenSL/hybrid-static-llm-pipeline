#!/usr/bin/env python3
"""End-to-end experimental architecture diagram (updated: four arms incl. grounded vs ungrounded,
verified-repair, and the three whole-solution quality-impact layers). Vector output: SVG + PDF + PNG."""
from __future__ import annotations
import argparse, sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

INK, EDGE, ARR, GREY = "#1a1a1a", "#5f6b76", "#5a5a5a", "#6a6a6a"
F = {"corpus": "#eceff1", "detect": "#e2eefb", "arm": "#fdecd6",
     "verify": "#e1f2e6", "layer": "#dcefec", "analysis": "#efe6f6"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=Path("output/figures"))
    ap.add_argument("--name", type=str, default="fig_architecture")
    args = ap.parse_args(argv)

    fig, ax = plt.subplots(figsize=(12, 9), dpi=300)
    ax.set_xlim(0, 14); ax.set_ylim(1.05, 14.4); ax.axis("off")

    def box(cx, cy, w, h, title, body, fill, title_fs=10, body_fs=7.6):
        ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                     boxstyle="round,pad=0.015,rounding_size=0.10", lw=1.1,
                     edgecolor=EDGE, facecolor=fill, mutation_aspect=1.0, zorder=2))
        ax.text(cx, cy + h / 2 - 0.20, title, ha="center", va="top", fontsize=title_fs,
                fontweight="bold", color=INK, zorder=3)
        if body:
            ax.text(cx, cy + h / 2 - 0.20 - title_fs / 20 - 0.18, body, ha="center", va="top",
                    fontsize=body_fs, color="#222", linespacing=1.25, zorder=3)
        return dict(cx=cx, cy=cy, w=w, h=h)

    def hdr(cx, y, txt):
        ax.text(cx, y, txt, ha="center", va="center", fontsize=8.4, style="italic", color=GREY,
                zorder=5, bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="none"))

    def arr(a, b, ax_, ay, bx, by, dashed=False, label=None, lpos=0.5, la="left"):
        p = FancyArrowPatch((ax_, ay), (bx, by), arrowstyle="-|>", mutation_scale=12, lw=1.3,
                            color=ARR, linestyle=(0, (4, 2)) if dashed else "-", zorder=1,
                            shrinkA=1, shrinkB=1)
        ax.add_patch(p)
        if label:
            ax.text(ax_ + (bx - ax_) * lpos + (0.15 if la == "left" else -0.15),
                    ay + (by - ay) * lpos, label, fontsize=6.8, style="italic", color=GREY, ha=la, va="center",
                    zorder=5, bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor="none"))

    # ── nodes ────────────────────────────────────────────────────────────
    corpus = box(7, 13.35, 11.4, 1.55, "Constructed corpus  (frozen)",
                 "30 seeded instances: 10 God Class · 10 Long Method · 10 Obsolete API\n"
                 "+ control & distractor files, with per-instance ground truth", F["corpus"], body_fs=8)
    detect = box(7, 11.55, 11.4, 1.4, "Detection — static analyser",
                 "God Class · Long Method · Obsolete API detectors  →  findings + triggering metrics",
                 F["detect"], body_fs=8)

    ac = [2.15, 5.38, 8.62, 11.85]
    analyser = box(ac[0], 9.35, 3.05, 2.0, "Analyser-only",
                   "raw diagnostic\n(no LLM · no repair)", F["arm"], title_fs=9, body_fs=7.2)
    hybrid = box(ac[1], 9.35, 3.05, 2.0, "Hybrid",
                 "finding + Minimal\ncontext → LLM\nsuggestion → strict-\nliteral applier\n"
                 "grounded · single-pass", F["arm"], title_fs=9, body_fs=7.0)
    grounded = box(ac[2], 9.35, 3.05, 2.0, "Grounded-iterative",
                   "finding → agent loop\n(edit ↔ compiler)\n\ngrounded · iterative",
                   F["arm"], title_fs=9, body_fs=7.0)
    agentic = box(ac[3], 9.35, 3.05, 2.0, "Agentic",
                  "unannotated file →\nagent loop\n(edit ↔ compiler)\nungrounded · iterative",
                  F["arm"], title_fs=9, body_fs=7.0)
    hdr(7, 7.95, "four architecture arms — a 2×2 of grounding × control structure  (H1a / H1b / H1c)")

    verify = box(7, 6.7, 12.2, 1.6, "Verified repair",
                 "apply / agent edit  →  dotnet build gate  →  re-measure triggering metric\n"
                 "ladder:  unapplicable  <  build-fails  <  builds-unresolved  <  resolved",
                 F["verify"], body_fs=8)
    hdr(7, 5.5, "Whole-solution quality impact — before → after, against the pristine baseline")

    lc = [2.7, 7, 11.3]
    l1 = box(lc[0], 4.3, 3.85, 1.95, "Layer 1",
             "own detectors,\nwhole solution\nsmell counts\n(self-scored)", F["layer"], title_fs=9, body_fs=7.2)
    l2 = box(lc[1], 4.3, 3.85, 1.95, "Layer 2",
             ".NET analysers\n(independent)\nCA headline/all + CS0618/9\n→ ISO/IEC 25010", F["layer"], title_fs=9, body_fs=7.0)
    l3 = box(lc[2], 4.3, 3.85, 1.95, "Layer 3",
             "characterisation tests\nbehavioural preservation\n(golden-master / smoke)", F["layer"], title_fs=9, body_fs=7.2)

    analysis = box(7, 2.2, 12.2, 1.5, "Analysis",
                   "detection recall & precision · verified-repair (H1a/H1b/H1c, 2×2) · quality impact · behaviour", F["analysis"], body_fs=8)

    # ── edges ────────────────────────────────────────────────────────────
    def bot(n): return (n["cx"], n["cy"] - n["h"] / 2)
    def top(n): return (n["cx"], n["cy"] + n["h"] / 2)

    arr(corpus, detect, *bot(corpus), *top(detect))
    for a in (analyser, hybrid, grounded):
        arr(detect, a, detect["cx"] + (a["cx"] - detect["cx"]) * 0.0, detect["cy"] - detect["h"] / 2, a["cx"], top(a)[1])
    arr(detect, agentic, detect["cx"], detect["cy"] - detect["h"] / 2, agentic["cx"], top(agentic)[1],
        dashed=True, label="finding withheld", lpos=0.55)
    # arms -> verify (converge near verify top)
    arr(analyser, verify, *bot(analyser), 3.0, verify["cy"] + verify["h"] / 2, dashed=True, label="no repair", lpos=0.5, la="right")
    arr(hybrid, verify, *bot(hybrid), 5.6, verify["cy"] + verify["h"] / 2)
    arr(grounded, verify, *bot(grounded), 8.4, verify["cy"] + verify["h"] / 2)
    arr(agentic, verify, *bot(agentic), 11.0, verify["cy"] + verify["h"] / 2)
    # verify -> layers
    for l in (l1, l2, l3):
        arr(verify, l, l["cx"], verify["cy"] - verify["h"] / 2, l["cx"], top(l)[1])
    # layers -> analysis
    for l in (l1, l2, l3):
        arr(l, analysis, *bot(l), l["cx"], analysis["cy"] + analysis["h"] / 2)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for ext in ("svg", "pdf", "png"):
        fig.savefig(args.out_dir / f"{args.name}.{ext}", bbox_inches="tight", facecolor="white", dpi=300)
    plt.close(fig)
    print(f"wrote {args.out_dir / (args.name + '.svg')} (+ .pdf, .png)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
