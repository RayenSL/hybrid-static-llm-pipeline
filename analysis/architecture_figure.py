#!/usr/bin/env python3
"""Figure 5.1: end-to-end generated-test factorial architecture.

The diagram separates the pre-repair LLM-generated visible characterisation
test from the hidden, author-written Layer 3 behavioural oracle. It renders the
four repair architectures and their test OFF/ON variants, followed by common
verification, objective quality layers, and statistical analysis.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

INK = "#1a1a1a"
BODY = "#292929"
EDGE = "#66727d"
ARROW = "#5c6268"
MUTED = "#66707a"
FILL = {
    "corpus": "#eceff1",
    "detect": "#dfeefa",
    "control": "#e8e3f2",
    "test": "#fff0c9",
    "campaign": "#fffaf3",
    "arm": "#fde7cf",
    "verify": "#dff1e5",
    "layer": "#d9efec",
    "private": "#cfe8e7",
    "analysis": "#eee3f5",
}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("output/figures"))
    parser.add_argument("--name", default="fig5_1_e2e_architecture")
    args = parser.parse_args(argv)

    fig, ax = plt.subplots(figsize=(13, 11), dpi=300)
    ax.set_xlim(0, 14)
    ax.set_ylim(0.7, 16.75)
    ax.axis("off")

    def box(cx, cy, width, height, title, body, fill, *, title_size=9.2,
            body_size=7.1, edge=EDGE, line_width=1.05, radius=0.10):
        patch = FancyBboxPatch(
            (cx - width / 2, cy - height / 2), width, height,
            boxstyle=f"round,pad=0.018,rounding_size={radius}",
            linewidth=line_width, edgecolor=edge, facecolor=fill, zorder=2,
        )
        ax.add_patch(patch)
        ax.text(cx, cy + height / 2 - 0.18, title, ha="center", va="top",
                fontsize=title_size, fontweight="bold", color=INK, zorder=3)
        if body:
            ax.text(cx, cy + height / 2 - 0.68, body, ha="center", va="top",
                    fontsize=body_size, color=BODY, linespacing=1.25, zorder=3)
        return {"cx": cx, "cy": cy, "w": width, "h": height}

    def arrow(start, end, *, dashed=False, label=None, label_xy=None):
        patch = FancyArrowPatch(
            start, end, arrowstyle="-|>", mutation_scale=11, linewidth=1.2,
            color=ARROW, linestyle=(0, (4, 2)) if dashed else "-",
            shrinkA=1, shrinkB=1, zorder=1,
        )
        ax.add_patch(patch)
        if label and label_xy:
            ax.text(*label_xy, label, ha="center", va="center", fontsize=6.6,
                    style="italic", color=MUTED,
                    bbox=dict(boxstyle="round,pad=0.20", facecolor="white", edgecolor="none"),
                    zorder=5)

    def top(node):
        return node["cx"], node["cy"] + node["h"] / 2

    def bottom(node):
        return node["cx"], node["cy"] - node["h"] / 2

    corpus = box(
        7, 15.75, 12.2, 1.15, "Constructed corpus (frozen)",
        "30 seeded instances: 10 God Class - 10 Long Method - 10 Obsolete API"
        "\n20 Long Method/God Class instances enter the generated-test factorial experiment",
        FILL["corpus"], body_size=7.5,
    )
    detector = box(
        2.50, 13.95, 4.00, 1.50, "Detection - static analyser",
        "Roslyn detector locates each instance"
        "\nand records type, severity, metrics,"
        "\nthresholds, symbol, and line range",
        FILL["detect"], body_size=6.9,
    )
    controller = box(
        7.00, 13.95, 3.60, 1.50, "Experiment controller",
        "Freezes two views"
        "\nNeutral: symbol + line range"
        "\nFull: diagnosis + metrics",
        FILL["control"], body_size=6.9,
    )
    test_author = box(
        11.50, 13.95, 4.00, 1.50, "Separate test-authoring call",
        "Pristine source + neutral view"
        "\nBefore repair; one attempt"
        "\nNo diagnosis, metrics, repair, or private oracle",
        FILL["test"], title_size=8.7, body_size=6.8,
    )
    admission = box(
        11.50, 12.45, 4.00, 1.05, "Visible-test admission and freeze",
        "Assertion gate -> compile -> two pristine runs"
        "\nFreeze source, target, and test hashes; no retry",
        FILL["test"], title_size=8.2, body_size=6.5,
    )

    campaign_patch = FancyBboxPatch(
        (0.45, 7.90), 13.10, 3.90,
        boxstyle="round,pad=0.025,rounding_size=0.14",
        linewidth=1.15, edgecolor="#a87942", facecolor=FILL["campaign"], zorder=0,
    )
    ax.add_patch(campaign_patch)
    ax.text(7, 11.50, "Blocked 2 x 2 x 2 repair campaign", ha="center", va="center",
            fontsize=10.2, fontweight="bold", color=INK, zorder=3)
    ax.text(
        7, 11.08,
        "Inputs frozen before repair: neutral target to every cell - full finding + metrics to grounded cells only - "
        "visible test to test-ON cells only",
        ha="center", va="center", fontsize=7.0, color=MUTED, style="italic", zorder=3,
    )

    arm_centers = [2.05, 5.35, 8.65, 11.95]
    ungrounded_single = box(
        arm_centers[0], 9.55, 3.00, 2.35, "Target-only single-shot",
        "Source + neutral target\nModel diagnoses target\nOne repair call"
        "\nExternal build/test; no retry\nTests: OFF / ON",
        FILL["arm"], title_size=8.5, body_size=6.8,
    )
    grounded_single = box(
        arm_centers[1], 9.55, 3.00, 2.35, "Detector-grounded single-shot",
        "Same target + full finding/metrics\nOne repair call\nExternal build/test"
        "\nNo repair retry\nTests: OFF / ON",
        FILL["arm"], title_size=8.5, body_size=6.8,
    )
    ungrounded_iterative = box(
        arm_centers[2], 9.55, 3.00, 2.35, "Target-only iterative",
        "Source + neutral target\nAgent diagnoses target\nEdit -> build feedback"
        "\n+ test result when ON\nBudget: 6 builds",
        FILL["arm"], title_size=8.5, body_size=6.8,
    )
    grounded_iterative = box(
        arm_centers[3], 9.55, 3.00, 2.35, "Detector-grounded iterative",
        "Same target + full finding/metrics\nEdit -> build feedback"
        "\n+ test result when ON\nBudget: 6 builds",
        FILL["arm"], title_size=8.5, body_size=6.8,
    )
    ax.text(
        7, 8.14,
        "Test-enabled assignments remain in the intention-to-treat analysis when generation or admission fails",
        ha="center", va="center", fontsize=6.8, color=MUTED, style="italic", zorder=3,
    )

    verify = box(
        7, 6.75, 12.4, 1.45, "Common frozen final-source artifact and repair verification",
        "Apply final patch -> dotnet build -> re-measure triggering metric"
        "\nSingle-shot has no retry; iterative feedback contains compiler and assigned visible-test results only",
        FILL["verify"], body_size=7.4,
    )

    layer_centers = [2.70, 7.00, 11.30]
    layer1 = box(
        layer_centers[0], 4.55, 3.90, 1.85, "Layer 1 - own detectors",
        "Whole-solution smell counts\nTriggering metric resolved?\nPipeline-relative measure",
        FILL["layer"], title_size=8.7, body_size=7.0,
    )
    layer2 = box(
        layer_centers[1], 4.55, 3.90, 1.85, "Layer 2 - .NET analysers",
        "Independent CA and compiler rules\nBefore/after quality impact\nMapped to ISO/IEC 25010",
        FILL["layer"], title_size=8.7, body_size=7.0,
    )
    layer3 = box(
        layer_centers[2], 4.55, 3.90, 1.85, "Layer 3 - private behavioural oracle",
        "Author-written characterisation tests\nHidden until all repairs finish\nRegression judgment; no retry",
        FILL["private"], title_size=8.6, body_size=7.0, edge="#477d7b",
    )

    analysis = box(
        7, 2.25, 12.4, 1.70, "Statistical analysis",
        "Detection recall/precision - intention-to-treat strict success = build + metric resolved + private test pass"
        "\nGrounding * control structure * generated test - paired test-ON minus test-OFF risk differences"
        "\nTokens, calls, builds, tests, duration, and pipeline cost by experimental condition",
        FILL["analysis"], body_size=7.3,
    )

    arrow((4.65, 15.17), top(detector))
    arrow((9.35, 15.17), top(test_author))
    arrow((4.50, 13.95), (5.20, 13.95))
    arrow((8.80, 13.95), (9.50, 13.95), dashed=True,
          label="neutral view", label_xy=(9.15, 14.23))
    arrow(bottom(test_author), top(admission))
    arrow((6.65, bottom(controller)[1]), (6.65, 11.80), dashed=True,
          label="neutral view: every cell", label_xy=(5.72, 12.55))
    arrow((7.35, bottom(controller)[1]), (7.35, 11.80),
          label="full view: grounded only", label_xy=(8.32, 12.55))
    arrow(bottom(admission), (11.50, 11.80), dashed=True)
    arrow((7, 7.90), top(verify))
    for layer in (layer1, layer2, layer3):
        arrow((layer["cx"], verify["cy"] - verify["h"] / 2), top(layer))
        arrow(bottom(layer), (layer["cx"], analysis["cy"] + analysis["h"] / 2))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for extension in ("png", "svg", "pdf"):
        fig.savefig(args.out_dir / f"{args.name}.{extension}", bbox_inches="tight",
                    facecolor="white", dpi=300)
    plt.close(fig)
    print(f"wrote {args.out_dir / (args.name + '.png')} (+ .svg, .pdf)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
