"""
Thesis figures — regenerate the headline Phase-C figures from the analysed CSVs
(output/tables/*.csv, produced by analyse_results.py) plus the raw grounded trace.

Emits PNG (300 dpi) + SVG (vector, LaTeX-friendly) into output/figures/:
  fig1_h1c_2x2            grouped bars: grounding x control structure (H1c) + hybrid comparator
  fig2_h1c_interaction    LINE interaction plot: grounded vs ungrounded across single-pass -> iterative
  fig3_ladder             stacked bars: verified-repair outcome ladder by architecture
  fig4_h2b_context        LINE + CI band: verified-repair by context level (H2b)
  fig5_recall             bars + CI: agentic detection recall by anti-pattern

Usage:  python analysis/thesis_figures.py
"""
from __future__ import annotations
import sys, json, glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

TABLES = Path("output/tables")
FIGS = Path("output/figures"); FIGS.mkdir(parents=True, exist_ok=True)

# Palette (mid-tones that read in both light and dark; colour encodes meaning, not sequence).
TEAL, GRAY, BLUE = "#1baf7a", "#6f6e68", "#2a78d6"
AMBER, RED, LGRAY = "#d99000", "#d64a49", "#b0aea6"
INK, MUTED, GRID = "#2c2c2a", "#6f6e68", "#e1e0d9"

plt.rcParams.update({
    "font.size": 11, "font.family": "sans-serif",
    "axes.edgecolor": MUTED, "axes.linewidth": 0.8,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 12, "figure.dpi": 150, "svg.fonttype": "none",
})


def save(fig, name: str) -> None:
    for ext in ("png", "svg", "pdf"):
        fig.savefig(FIGS / f"{name}.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {name}.png / .svg / .pdf")


def fig1_and_2_from_2x2():
    d = pd.read_csv(TABLES / "verified_repair_2x2.csv")

    def cell(arm, snap):
        r = d[(d["arm"] == arm) & (d["snapshot"] == snap)].iloc[0]
        return float(r.success_pct), float(r.ci_lo_pct), float(r.ci_hi_pct)

    hyb = float(d[d["arm"] == "comparator"].iloc[0].success_pct)
    snaps = ["first_build", "final"]
    arms = [("grounded", TEAL, "o", "grounded"),
            ("ungrounded", GRAY, "s", "ungrounded (agentic)")]

    # ── Fig 1: grouped bars ──
    fig, ax = plt.subplots(figsize=(6.6, 4.1))
    x = np.arange(2); w = 0.36
    for i, (arm, color, _m, lab) in enumerate(arms):
        vals = [cell(arm, s)[0] for s in snaps]
        lo = [cell(arm, s)[1] for s in snaps]; hi = [cell(arm, s)[2] for s in snaps]
        err = [[v - l for v, l in zip(vals, lo)], [h - v for v, h in zip(vals, hi)]]
        xs = x + (i - 0.5) * w
        ax.bar(xs, vals, w, color=color, label=lab, zorder=3)
        ax.errorbar(xs, vals, yerr=err, fmt="none", ecolor=INK, elinewidth=1.2, capsize=4, zorder=4)
        for xi, v, h in zip(xs, vals, hi):
            ax.text(xi, h + 1.2, f"{v:.1f}", ha="center", va="bottom", fontsize=10)
    ax.axhline(hyb, ls="--", color=MUTED, lw=1.3, zorder=2)
    ax.text(1.42, hyb + 1, f"hybrid comparator {hyb:.1f}%", ha="right", va="bottom", fontsize=9.5, color=MUTED)
    ax.set_xticks(x); ax.set_xticklabels(["single pass\n(first build)", "iterative\n(final)"])
    ax.set_ylabel("verified-repair (%)"); ax.set_ylim(0, 70)
    ax.legend(frameon=False, loc="upper left")
    ax.set_title("Verified-repair by grounding × control structure (H1c)")
    ax.grid(axis="x", visible=False)
    save(fig, "fig1_h1c_2x2")

    # ── Fig 2: interaction line plot ──
    fig, ax = plt.subplots(figsize=(6.2, 4.1))
    xp = [0, 1]
    for arm, color, mark, lab in arms:
        vals = [cell(arm, s)[0] for s in snaps]
        lo = [cell(arm, s)[1] for s in snaps]; hi = [cell(arm, s)[2] for s in snaps]
        err = [[v - l for v, l in zip(vals, lo)], [h - v for v, h in zip(vals, hi)]]
        ax.errorbar(xp, vals, yerr=err, color=color, marker=mark, ms=7, lw=2.2,
                    capsize=4, label=lab, zorder=3)
        for xi, v in zip(xp, vals):
            ax.annotate(f"{v:.1f}", (xi, v), textcoords="offset points",
                        xytext=(0, 8), ha="center", fontsize=9.5, color=color)
    ax.axhline(hyb, ls="--", color=BLUE, lw=1.2, zorder=2)
    ax.text(-0.28, hyb + 1.2, f"hybrid {hyb:.1f}%", color=BLUE, fontsize=9, ha="left", va="bottom")
    ax.set_xticks(xp); ax.set_xticklabels(["single pass", "iterative"])
    ax.set_xlim(-0.3, 1.3); ax.set_ylabel("verified-repair (%)"); ax.set_ylim(0, 70)
    ax.legend(frameon=False, loc="lower right")
    ax.set_title("Grounding × iteration interaction")
    ax.grid(axis="x", visible=False)
    save(fig, "fig2_h1c_interaction")


def fig3_ladder():
    arch = pd.read_csv(TABLES / "verified_repair_by_architecture.csv").set_index("architecture")
    order = ["resolved", "builds_unresolved", "build_fails", "unapplicable"]
    colors = {"resolved": TEAL, "builds_unresolved": AMBER, "build_fails": RED, "unapplicable": LGRAY}
    light_text = {"resolved", "build_fails"}

    grounded = {k: 0 for k in order}
    for p in glob.glob("runs/*-grounded-iterative.jsonl"):
        for line in open(p, encoding="utf-8-sig"):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("agentic_snapshot") == "final" and r.get("verified_repair_ladder"):
                grounded[r["verified_repair_ladder"]] += 1

    rows = [
        ("grounded-iterative", grounded),
        ("hybrid (applied)", {k: int(arch.loc["hybrid", k]) for k in order}),
        ("agentic (ungrounded)", {k: int(arch.loc["agentic", k]) for k in order}),
    ]
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    for i, (_name, dist) in enumerate(rows):
        left = 0.0; tot = sum(dist.values()) or 1
        for k in order:
            pct = 100 * dist[k] / tot
            ax.barh(i, pct, left=left, height=0.62, color=colors[k], zorder=3)
            if pct >= 8:
                ax.text(left + pct / 2, i, f"{pct:.0f}%", ha="center", va="center",
                        fontsize=9, color=("white" if k in light_text else INK))
            left += pct
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 100); ax.set_xlabel("share of instances (%)  (n = 90 per arm, Minimal grounding)")
    ax.legend(handles=[Patch(color=colors[k], label=k.replace("_", "-")) for k in order],
              frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.28), fontsize=9)
    ax.set_title("Verified-repair outcome ladder by architecture")
    ax.grid(axis="y", visible=False)
    save(fig, "fig3_ladder")


def fig4_h2b_context():
    ctx = pd.read_csv(TABLES / "verified_repair_by_context.csv").sort_values("context_ord")
    fig, ax = plt.subplots(figsize=(6.4, 4.1))
    xp = ctx["context_ord"].to_numpy()
    y = ctx["success_pct"].to_numpy(); lo = ctx["ci_lo_pct"].to_numpy(); hi = ctx["ci_hi_pct"].to_numpy()
    ax.fill_between(xp, lo, hi, color=BLUE, alpha=0.12, zorder=1, label="95% Wilson CI")
    ax.plot(xp, y, color=BLUE, lw=2.4, marker="o", ms=7, zorder=3)
    for xi, v in zip(xp, y):
        ax.annotate(f"{v:.1f}", (xi, v), textcoords="offset points", xytext=(0, 9),
                    ha="center", fontsize=9.5, color=BLUE)
    ax.set_xticks(xp); ax.set_xticklabels(ctx["context_level"])
    ax.set_ylabel("verified-repair (%)"); ax.set_ylim(0, 70)
    ax.set_title("Verified-repair by context level (H2b) — no monotonic trend")
    ax.text(0.03, 0.07, "Cochran–Armitage z = −0.58, p = 0.56",
            transform=ax.transAxes, fontsize=9.5, color=MUTED)
    ax.legend(frameon=False, loc="upper right")
    ax.grid(axis="x", visible=False)
    save(fig, "fig4_h2b_context")


def fig5_recall():
    rec = pd.read_csv(TABLES / "agentic_recall.csv")
    rec = rec[rec["anti_pattern_type"] != "ALL"].reset_index(drop=True)
    names = [t.replace("_", " ") for t in rec["anti_pattern_type"]]
    vals = rec["recall"].to_numpy() * 100
    lo = rec["ci_lo"].to_numpy() * 100; hi = rec["ci_hi"].to_numpy() * 100
    fig, ax = plt.subplots(figsize=(6.0, 4.1))
    ax.bar(names, vals, width=0.55, color=BLUE, zorder=3)
    ax.errorbar(names, vals, yerr=[vals - lo, hi - vals], fmt="none", ecolor=INK,
                elinewidth=1.2, capsize=4, zorder=4)
    for i, v in enumerate(vals):
        ax.text(i, hi[i] + 2, f"{v:.0f}%", ha="center", fontsize=10)
    ax.set_ylabel("detection recall (%)"); ax.set_ylim(0, 108)
    ax.set_title("Agentic detection recall by anti-pattern")
    ax.grid(axis="x", visible=False)
    save(fig, "fig5_recall")


def fig6_ladder_by_context():
    """Hybrid repair-outcome ladder by context level — the composition behind H2b's flat trend
    (unapplicable stable, build-fails rising, resolved drifting down). Computed from the hybrid
    verify-repair trace since the by-context CSV keeps only the resolved count."""
    order = ["resolved", "builds_unresolved", "build_fails", "unapplicable"]
    colors = {"resolved": TEAL, "builds_unresolved": AMBER, "build_fails": RED, "unapplicable": LGRAY}
    light_text = {"resolved", "build_fails"}
    levels = ["minimal", "structural", "relational", "full"]

    byctx = {lvl: {k: 0 for k in order} for lvl in levels}
    for p in glob.glob("runs/*-verified.jsonl"):
        for line in open(p, encoding="utf-8-sig"):
            if not line.strip():
                continue
            r = json.loads(line)
            lvl = r.get("context_level")
            if r.get("architecture") == "hybrid" and lvl in byctx and r.get("verified_repair_ladder"):
                byctx[lvl][r["verified_repair_ladder"]] += 1

    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    for i, lvl in enumerate(levels):
        dist = byctx[lvl]; left = 0.0
        for k in order:
            v = dist[k]
            ax.barh(i, v, left=left, height=0.62, color=colors[k], zorder=3)
            if v >= 4:
                ax.text(left + v / 2, i, str(v), ha="center", va="center",
                        fontsize=9, color=("white" if k in light_text else INK))
            left += v
    ax.set_yticks(range(len(levels))); ax.set_yticklabels(levels)
    ax.invert_yaxis()
    ax.set_xlim(0, 90); ax.set_xlabel("instances (n = 90 per context level)")
    ax.legend(handles=[Patch(color=colors[k], label=k.replace("_", "-")) for k in order],
              frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.26), fontsize=9)
    ax.set_title("Hybrid repair-outcome ladder by context level (H2b)")
    ax.grid(axis="y", visible=False)
    save(fig, "fig6_ladder_by_context")


if __name__ == "__main__":
    if not (TABLES / "verified_repair_2x2.csv").exists():
        print("error: run analyse_results.py first (output/tables/*.csv missing)", file=sys.stderr)
        raise SystemExit(2)
    print(f"writing figures to {FIGS.resolve()}")
    fig1_and_2_from_2x2()
    fig3_ladder()
    fig4_h2b_context()
    fig5_recall()
    fig6_ladder_by_context()
    print("done.")
