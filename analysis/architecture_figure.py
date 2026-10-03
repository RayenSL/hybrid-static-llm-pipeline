#!/usr/bin/env python3
"""Figure 5.1: end-to-end experimental architecture.

The diagram renders the pipeline as currently specified in the thesis. Static
analysis detects the target and constructs the nested context payloads. Its
Structural payload is exposed only to grounded factorial cells, while all four
payloads feed the context-ladder runs. Diagnosis-blind generated tests are a
confirmatory factor only; the context-ladder runs instead use separately frozen,
author-written behavioural oracles after repair.
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
CONFIRM_EDGE = "#a87942"
SUPP_EDGE = "#5f7ea8"
FILL = {
    "corpus": "#eceff1",
    "detect": "#dfeefa",
    "control": "#e8e3f2",
    "test": "#fff0c9",
    "campaign": "#fffaf3",
    "supplement": "#f5f8fc",
    "arm": "#fde7cf",
    "hybrid": "#dfe7f4",
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

    fig, ax = plt.subplots(figsize=(13.6, 12.95), dpi=300)
    ax.set_xlim(0, 14)
    ax.set_ylim(1.70, 18.65)
    ax.axis("off")

    def box(cx, cy, width, height, title, body, fill, *, title_size=9.0,
            body_size=6.9, edge=EDGE, line_width=1.05, radius=0.10,
            title_gap=0.19, body_gap=0.64):
        patch = FancyBboxPatch(
            (cx - width / 2, cy - height / 2), width, height,
            boxstyle=f"round,pad=0.018,rounding_size={radius}",
            linewidth=line_width, edgecolor=edge, facecolor=fill, zorder=2,
        )
        ax.add_patch(patch)
        ax.text(cx, cy + height / 2 - title_gap, title, ha="center", va="top",
                fontsize=title_size, fontweight="bold", color=INK, zorder=3,
                linespacing=1.15)
        if body:
            ax.text(cx, cy + height / 2 - body_gap, body, ha="center", va="top",
                    fontsize=body_size, color=BODY, linespacing=1.28, zorder=3)
        return {"cx": cx, "cy": cy, "w": width, "h": height}

    def arrow(start, end, *, dashed=False, color=ARROW):
        ax.add_patch(FancyArrowPatch(
            start, end, arrowstyle="-|>", mutation_scale=11, linewidth=1.2,
            color=color, linestyle=(0, (4, 2)) if dashed else "-",
            shrinkA=1, shrinkB=1, zorder=1,
        ))

    def line(xs, ys, *, dashed=False, color=ARROW):
        ax.plot(xs, ys, color=color, linewidth=1.2,
                linestyle=(0, (4, 2)) if dashed else "-", zorder=1,
                solid_capstyle="round")

    def note(x, y, text, *, size=6.5, boxed=True):
        ax.text(x, y, text, ha="center", va="center", fontsize=size,
                style="italic", color=MUTED, zorder=5,
                bbox=dict(boxstyle="round,pad=0.20", facecolor="white",
                          edgecolor="none") if boxed else None)

    def top(node):
        return node["cx"], node["cy"] + node["h"] / 2

    def bottom(node):
        return node["cx"], node["cy"] - node["h"] / 2

    # ----------------------------------------------------- codebase and detection
    codebase = box(
        4.55, 17.70, 8.30, 1.45, "Codebase under analysis (frozen revision)",
        "Any independently compilable solution: an industrial or open-source repository, or a constructed evaluation corpus"
        "\nThe pipeline needs buildable source only; seeded ground truth is an evaluation requirement, not an operating one"
        "\nDetection, repair, verification and Layers 1-2 transfer unchanged; Layer 3 needs a characterisation suite for the targeted code",
        FILL["corpus"], title_size=9.6, body_size=6.8, body_gap=0.72,
    )
    instance = box(
        11.40, 17.70, 4.50, 1.45, "Evaluation populations (this study)",
        "Constructed corpus v2.0: 36 confirmed targets"
        "\n13 God Class - 13 Long Method - 10 Obsolete API"
        "\n37 control and distractor files; seeded ground truth"
        "\nIndustrial repository (Ibis): 9 assigned targets"
        "\n8 Long Method - 1 God Class",
        FILL["corpus"], title_size=8.9, body_size=6.4, body_gap=0.58,
    )
    detection = box(
        4.55, 15.85, 8.30, 1.50, "Detection and nested context construction - static analyser",
        "Minimal: anti-pattern label + code fragment | Structural: + diagnosis, metrics and thresholds"
        "\nRelational: + enclosing declaration and source window | Full: + Referenced type declarations"
        "\nFull cap: 8 files / 60,000 characters; detector finding retains symbol and line range",
        FILL["detect"], title_size=9.0, body_size=6.6, body_gap=0.72,
    )
    detector_role = box(
        11.40, 15.85, 4.50, 1.50, "Payload routing and detector roles",
        "Structural only to grounded factorial cells"
        "\nNeutral coordinates to ungrounded factorial cells"
        "\nAll four payloads to context-ladder runs"
        "\nRe-measures the triggering condition after repair"
        "\nCorpus-only recall/precision check; never a repair arm",
        FILL["detect"], title_size=8.5, body_size=6.1, body_gap=0.57,
    )

    panel_y0, panel_y1 = 7.25, 12.75

    shared_tests = box(
        4.60, 14.25, 6.80, 1.15,
        "Confirmatory diagnosis-blind test generation and admission",
        "Pristine source + test-project skeleton + neutral coordinates; freeze after three successful pristine passes"
        "\nOne frozen five-case suite per factorial target"
        "\nVisible only to test-ON factorial assignments",
        FILL["test"], title_size=8.8, body_size=6.0, body_gap=0.55,
    )

    # ------------------------------------------- confirmatory factorial panel
    confirm_x0, confirm_x1 = 0.35, 8.85
    ax.add_patch(FancyBboxPatch(
        (confirm_x0, panel_y0), confirm_x1 - confirm_x0, panel_y1 - panel_y0,
        boxstyle="round,pad=0.025,rounding_size=0.14",
        linewidth=1.15, edgecolor=CONFIRM_EDGE, facecolor=FILL["campaign"], zorder=0,
    ))
    confirm_cx = (confirm_x0 + confirm_x1) / 2
    ax.text(confirm_cx, 12.51, "Confirmatory 2 x 2 x 2 direct-editing factorial",
            ha="center", va="center", fontsize=10.0, fontweight="bold",
            color=INK, zorder=3)
    ax.text(
        confirm_cx, 12.08,
        "26 God Class and Long Method targets x 3 repetitions x 8 cells = 624 assignments"
        "\ngpt-5.6-sol edits production source directly; the factorial has no separate applier"
        "\nNeutral coordinates to every cell - Structural finding to grounded cells only - visible test to test-ON cells only",
        ha="center", va="center", fontsize=6.5, color=MUTED, style="italic",
        linespacing=1.35, zorder=3,
    )

    controller = box(
        confirm_cx, 10.88, 7.70, 1.25, "Experiment controller",
        "Frozen assignment manifest, seed 20260812"
        "\nFreezes payload view, repair contract and test OFF / ON assignment"
        "\nInterleaves cells; failures stay in their assigned denominator",
        FILL["control"], title_size=8.9, body_size=6.4, body_gap=0.58,
    )

    arm_centers = [1.47, 3.58, 5.69, 7.80]
    arm_w, arm_cy, arm_h = 1.98, 8.72, 2.35
    box(
        arm_centers[0], arm_cy, arm_w, arm_h, "Ungrounded\nsingle-shot",
        "Pristine source and\nneutral coordinates"
        "\nModel must diagnose\nthe target itself"
        "\nOne production-edit call"
        "\nNo execution feedback"
        "\nTest OFF / ON",
        FILL["arm"], title_size=8.2, body_size=6.4, body_gap=0.88,
    )
    box(
        arm_centers[1], arm_cy, arm_w, arm_h, "Grounded\nsingle-shot",
        "Same payload plus the\nStructural detector"
        "\nfinding (diagnosis)"
        "\nOne production-edit call"
        "\nNo execution feedback"
        "\nTest OFF / ON",
        FILL["arm"], title_size=8.2, body_size=6.4, body_gap=0.88,
    )
    box(
        arm_centers[2], arm_cy, arm_w, arm_h, "Ungrounded\niterative",
        "Pristine source and\nneutral coordinates"
        "\nUp to 6 model calls"
        "\nCompiler feedback after"
        "\neach proposed state"
        "\n+ visible-test result\nwhen ON"
        "\nTest OFF / ON",
        FILL["arm"], title_size=8.2, body_size=6.4, body_gap=0.88,
    )
    box(
        arm_centers[3], arm_cy, arm_w, arm_h, "Grounded\niterative",
        "Same payload plus the\nStructural detector"
        "\nfinding (diagnosis)"
        "\nUp to 6 model calls"
        "\nCompiler feedback and,"
        "\nwhen ON, visible-test\nresults"
        "\nTest OFF / ON",
        FILL["arm"], title_size=8.2, body_size=6.4, body_gap=0.88,
    )
    # ------------------------------------------------ context-ladder panel
    supp_x0, supp_x1 = 9.15, 13.65
    ax.add_patch(FancyBboxPatch(
        (supp_x0, panel_y0), supp_x1 - supp_x0, panel_y1 - panel_y0,
        boxstyle="round,pad=0.025,rounding_size=0.14",
        linewidth=1.15, edgecolor=SUPP_EDGE, facecolor=FILL["supplement"], zorder=0,
    ))
    supp_cx = (supp_x0 + supp_x1) / 2
    ax.text(supp_cx, 12.51, "Direct-editing context-ladder experiments",
            ha="center", va="center", fontsize=8.5, fontweight="bold",
            color=INK, zorder=3)
    ax.text(
        supp_cx, 12.10,
        "ladder-v2.0.0 - gpt-5.6-sol - single-shot"
        "\nVisible tests OFF; no build or test feedback",
        ha="center", va="center", fontsize=6.3, color=MUTED, style="italic",
        linespacing=1.35, zorder=3,
    )

    corpus_run = box(
        10.28, 10.62, 1.92, 1.22, "Corpus run",
        "36 targets x 4 levels"
        "\nx 3 repetitions"
        "\n= 432 assignments"
        "\nMatched inference",
        FILL["hybrid"], title_size=8.0, body_size=5.9, body_gap=0.52,
    )
    industrial_run = box(
        12.52, 10.62, 1.92, 1.22, "Ibis run",
        "9 targets x 4 levels"
        "\nx 3 repetitions"
        "\n= 108 assignments"
        "\nDescriptive only",
        FILL["hybrid"], title_size=8.0, body_size=5.9, body_gap=0.52,
    )
    direct_edit = box(
        supp_cx, 8.78, 4.10, 1.52, "Direct production-source editing",
        "One complete edited file per call"
        "\nNo separate applier"
        "\nFailures stay in their assigned denominator",
        FILL["hybrid"], title_size=8.5, body_size=6.5, body_gap=0.58,
    )
    note(supp_cx, 7.51,
         "Separate manifests and denominators; never pooled",
         size=6.5, boxed=False)

    # ------------------------------------------------------------ verification
    verify = box(
        7, 6.30, 13.20, 1.15, "Common frozen final state and repair verification",
        "Seal the final source state (archived diff + checksum) -> dotnet build gate -> re-measure the triggering detector metric"
        "\nDetector remeasurement, private testing and whole-solution analysis run only after sealing, and are withheld from every repair call",
        FILL["verify"], title_size=9.4, body_size=7.1,
    )

    layer_centers = [2.65, 7.00, 11.35]
    layer1 = box(
        layer_centers[0], 4.55, 4.10, 1.55, "Layer 1 - own detectors",
        "Whole-solution smell counts"
        "\nTriggering metric resolved?"
        "\nCollateral change by file and category"
        "\nSame-taxonomy check (self-scored)",
        FILL["layer"], title_size=8.7, body_size=6.9, body_gap=0.70,
    )
    layer2 = box(
        layer_centers[1], 4.55, 4.10, 1.55, "Layer 2 - .NET analysers",
        "Independent CA rules, CS0618 / CS0619"
        "\nHeadline and all-rules tiers"
        "\nDedicated analyser build, outside the gate"
        "\nMapped to ISO/IEC 25010",
        FILL["layer"], title_size=8.7, body_size=6.9, body_gap=0.70,
    )
    layer3 = box(
        layer_centers[2], 4.55, 4.10, 1.55, "Layer 3 - private behavioural oracle",
        "Corpus: frozen author-written characterisation drivers"
        "\nIbis: frozen author-written 90-driver golden-master harness"
        "\nNever supplied to the repair model"
        "\nExecuted only after each campaign is sealed",
        FILL["private"], title_size=8.5, body_size=6.2, body_gap=0.60,
        edge="#477d7b",
    )

    analysis = box(
        7, 2.66, 13.20, 1.65, "Analysis - separate denominators, never pooled",
        "Confirmatory: strict success = build AND triggering detector resolved AND private oracle passed; the primary estimand is the"
        "\ntarget-level visible-test main effect, with grounding and control structure as planned secondary effects"
        "\nCorpus ladder: verified repair = build AND detector resolved; Cochran Q and exact McNemar, Holm-adjusted"
        "\nIndustrial ladder: the same endpoint and an external oracle, reported descriptively without a p-value"
        "\nDetection recall and precision manipulation check - whole-solution quality impact - tokens, calls, builds and duration by condition",
        FILL["analysis"], title_size=9.4, body_size=6.4,
    )

    # ----------------------------------------------------------------- arrows
    arrow(bottom(codebase), top(detection))
    arrow((8.70, 17.70), (9.15, 17.70), dashed=True)
    arrow((8.70, 15.85), (9.15, 15.85), dashed=True)

    # Detection constructs the payloads; arrow labels state what each experiment sees.
    arrow((4.55, 15.10), top(shared_tests))
    arrow((2.20, 15.10), (2.20, panel_y1))
    note(1.78, 13.58, "Structural only to\ngrounded factorial cells", size=6.0)
    arrow((11.40, 15.10), (11.40, panel_y1))
    note(11.82, 13.58, "All four payloads to\ncontext-ladder runs", size=6.0)

    # The generated test artefact is a confirmatory factor only.
    arrow((5.35, bottom(shared_tests)[1]), (5.35, panel_y1), dashed=True)
    note(5.35, 13.22, "test-ON only", size=5.9)

    # assignment rail: controller payloads and the admitted visible test
    rail_y = 10.08
    line([arm_centers[0], arm_centers[-1]], [rail_y, rail_y])
    line([confirm_cx, confirm_cx], [bottom(controller)[1], rail_y])
    for cx in arm_centers:
        arrow((cx, rail_y), (cx, arm_cy + arm_h / 2))

    arrow(bottom(corpus_run), (direct_edit["cx"] - 0.65, top(direct_edit)[1]))
    arrow(bottom(industrial_run), (direct_edit["cx"] + 0.65, top(direct_edit)[1]))

    arrow((confirm_cx, panel_y0), (confirm_cx, verify["cy"] + verify["h"] / 2))
    arrow((supp_cx, panel_y0), (supp_cx, verify["cy"] + verify["h"] / 2))

    for layer in (layer1, layer2, layer3):
        arrow((layer["cx"], bottom(verify)[1]), top(layer))
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
