"""
Thesis evaluation analyser — operates on the rated experiments file
(`experiments.jsonl`) produced by `score_runs.py` under the rubric defined in
Appendix B of the thesis.

What it produces (per Methodology §4.5–4.6 + Appendix B):

  * Descriptive proportions per ordinal level (poor / adequate / good) with
    Wilson 95% confidence intervals, grouped by:
      - context level   (→ H2a–c)
      - anti-pattern    (descriptive)
  * Hallucination-category occurrence rates with Wilson CIs (→ RQ1.2).
  * Quality-attribute alignment & incorrect-mention counts per anti-pattern
    (→ RQ1.3).
  * H1 baseline comparison: paired Cliff's δ between analyser-only and each
    hybrid context level, per dimension (→ H1).
  * Holm–Bonferroni correction is NOT applied to plotting; it is applied to
    pairwise tables where a single hypothesis family is reported.

What it deliberately does NOT do:

  * Cumulative-link mixed-effects models (CLMM). The thesis fits these in R
    (`ordinal::clmm`) because Python's `statsmodels` lacks a robust ordinal
    mixed-effects implementation. The CSV outputs of this script feed the R
    workflow.

Usage:
    python analyse_results.py --input experiments.jsonl --output output
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ── Schema (matches score_runs.py exactly) ────────────────────────────────────

ORDINAL_VALUES = ("poor", "adequate", "good")
ORDINAL_NUM = {"poor": 0, "adequate": 1, "good": 2}

EXPLANATION_DIMS = [
    "explanation_correctness",
    "explanation_groundedness",
    "explanation_completeness",
    "explanation_clarity",
]
REPAIR_DIMS = [
    "repair_correctness",
    "repair_completeness",
    "repair_actionability",
    "repair_semantic_risk",
]
ALL_DIMS = EXPLANATION_DIMS + REPAIR_DIMS

HALLUCINATION_CATEGORIES = [
    "factual_fabrication",
    "context_inconsistency",
    "intent_mismatch",
    "incomplete_suggestion",
    "irrelevant_suggestion",
    "risky_repair",
    "over_generalisation",
]

CONTEXT_LEVEL_ORDER = ["analyser_only", "minimal", "structural", "relational", "full"]

# Plot config — sober defaults, no seaborn.
FIG_SIZE = (8, 5)
DPI = 150
ORDINAL_COLOURS = {  # colour-blind safe traffic light
    "poor":     "#cf222e",
    "adequate": "#bf8700",
    "good":     "#1a7f37",
}


# ── Loading & cleaning ────────────────────────────────────────────────────────

def load(path: Path) -> pd.DataFrame:
    """Load JSONL / JSON / CSV. Auto-detects JSONL by content. UTF-8 BOM tolerant."""
    from io import StringIO
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(path, encoding="utf-8-sig")

    if suffix in (".jsonl", ".json"):
        with path.open("r", encoding="utf-8-sig") as fh:
            lines = [ln for ln in fh if ln.strip()]
        if not lines:
            return pd.DataFrame()
        try:
            return pd.read_json(StringIO("".join(lines)), lines=True)
        except ValueError:
            return pd.read_json(StringIO("".join(lines)))

    raise ValueError(f"unsupported file type: {suffix}")


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Lowercase ordinal values and context levels.
    for col in ALL_DIMS:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip().str.lower()
            df.loc[~df[col].isin(ORDINAL_VALUES), col] = pd.NA

    if "context_level" in df.columns:
        df["context_level"] = df["context_level"].astype(str).str.strip().str.lower()

    # Derive architecture if absent (older rows): analyser_only / hybrid / llm_only.
    if "architecture" not in df.columns:
        def _derive_arch(row):
            if str(row.get("model_name", "")).lower() == "static-analyser": return "analyser_only"
            if str(row.get("context_level", "")).lower() == "analyser_only": return "analyser_only"
            return "hybrid"
        df["architecture"] = df.apply(_derive_arch, axis=1)
    df["architecture"] = df["architecture"].astype(str).str.strip().str.lower()

    # Instance key for pairing across arms (file × symbol × line).
    if {"file_path", "symbol_name", "line"}.issubset(df.columns):
        df["instance_key"] = (
            df["file_path"].astype(str) + "::" +
            df["symbol_name"].astype(str) + "::" +
            df["line"].astype(str)
        )

    # Numeric counts.
    for col in ("attributes_correctly_aligned", "incorrectly_mentioned_attributes",
                "rating_duration_seconds", "line", "llm_reported_line"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Booleans. pandas may read these as float (1.0/0.0/NaN) when some rows omit the
    # field, so handle numeric truthiness explicitly (NaN → False).
    for col in ("is_spurious", "context_truncated", "refusal_detected"):
        if col in df.columns:
            df[col] = df[col].map(_to_bool)

    # Ensure hallucination_categories is a Python list per row (JSONL gives lists,
    # CSV may give strings).
    if "hallucination_categories" in df.columns:
        df["hallucination_categories"] = df["hallucination_categories"].apply(_ensure_list)

    return df


def _to_bool(v) -> bool:
    if isinstance(v, bool): return v
    if isinstance(v, (int, float)):
        return False if (isinstance(v, float) and math.isnan(v)) else bool(v)
    return str(v).strip().lower() in ("true", "1", "yes")


def _ensure_list(v) -> list:
    if isinstance(v, list): return v
    if v is None or (isinstance(v, float) and math.isnan(v)): return []
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
    return []


def has(df: pd.DataFrame, *cols: str) -> bool:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        warnings.warn(f"skipping — missing columns: {missing}", stacklevel=2)
        return False
    return True


# ── Statistical primitives ────────────────────────────────────────────────────

def wilson_ci(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson 95% CI for a binomial proportion. Returns (lo, hi). NaN on n=0."""
    if n == 0:
        return (float("nan"), float("nan"))
    from scipy.stats import norm
    z = norm.ppf(1 - alpha / 2)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def cliffs_delta(x: list[float], y: list[float]) -> tuple[float, str]:
    """
    Cliff's δ effect size for two independent ordinal samples.
    δ ∈ [-1, 1]. Interpretation thresholds per Romano et al. (2006).
    """
    if not x or not y:
        return (float("nan"), "n/a")
    gt = lt = 0
    for xi in x:
        for yj in y:
            if xi > yj: gt += 1
            elif xi < yj: lt += 1
    n = len(x) * len(y)
    delta = (gt - lt) / n
    mag = abs(delta)
    if   mag < 0.147: label = "negligible"
    elif mag < 0.330: label = "small"
    elif mag < 0.474: label = "medium"
    else:             label = "large"
    return (delta, label)


def holm_correct(pvals: list[float]) -> list[float]:
    """Holm–Bonferroni step-down correction. Returns corrected p-values in original order."""
    n = len(pvals)
    if n == 0: return []
    order = sorted(range(n), key=lambda i: pvals[i])
    corrected = [0.0] * n
    running_max = 0.0
    for rank, idx in enumerate(order):
        p_corr = min(1.0, pvals[idx] * (n - rank))
        running_max = max(running_max, p_corr)
        corrected[idx] = running_max
    return corrected


# ── Output helpers ────────────────────────────────────────────────────────────

def save_table(df: pd.DataFrame, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / f"{name}.csv", index=False)


def save_figure(fig: plt.Figure, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_dir / f"{name}.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def _ordered_categories(values: pd.Series, preferred: list[str]) -> list[str]:
    seen = list(values.dropna().astype(str).unique())
    head = [c for c in preferred if c in seen]
    tail = sorted([c for c in seen if c not in preferred])
    return head + tail


# ── Ordinal proportions (the core data view) ──────────────────────────────────

def proportions_per_level(df: pd.DataFrame, dim: str, group_col: str) -> pd.DataFrame:
    """
    For each group, returns one row with the proportion of poor/adequate/good
    plus Wilson 95% CIs. Long-format wide table — easy to plot or to read into R.
    """
    sub = df[[group_col, dim]].dropna()
    out_rows: list[dict] = []
    for g, gdf in sub.groupby(group_col):
        n = len(gdf)
        row = {"group": g, "n": n}
        for level in ORDINAL_VALUES:
            k = int((gdf[dim] == level).sum())
            p = k / n if n else float("nan")
            lo, hi = wilson_ci(k, n)
            row[f"{level}_n"]    = k
            row[f"{level}_prop"] = round(p, 4)
            row[f"{level}_lo"]   = round(lo, 4)
            row[f"{level}_hi"]   = round(hi, 4)
        out_rows.append(row)
    return pd.DataFrame(out_rows)


def stacked_proportion_chart(
    table: pd.DataFrame, dim: str, group_label: str, *, rotate: bool = False
) -> plt.Figure:
    """Horizontally-stacked bar chart of poor/adequate/good proportions."""
    groups = table["group"].astype(str).tolist()
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    bottom = np.zeros(len(groups))
    for level in ORDINAL_VALUES:
        vals = table[f"{level}_prop"].fillna(0).to_numpy()
        ax.bar(groups, vals, bottom=bottom, label=level, color=ORDINAL_COLOURS[level])
        bottom += vals
    ax.set_ylim(0, 1)
    ax.set_ylabel("Proportion")
    ax.set_xlabel(group_label)
    ax.set_title(f"{dim.replace('_', ' ')} by {group_label}")
    ax.legend(loc="upper right", framealpha=0.9)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    if rotate:
        ax.tick_params(axis="x", labelrotation=20)
    return fig


# ── Per-analysis blocks ──────────────────────────────────────────────────────

def overview(df: pd.DataFrame, tables_dir: Path) -> None:
    rows = {
        "rated_outputs":   [len(df)],
        "raters":          [df["rater_id"].nunique() if "rater_id" in df else None],
        "rubric_versions": [df["rubric_version"].nunique() if "rubric_version" in df else None],
        "refusals":        [int(df.get("refusal_detected", pd.Series([])).fillna(False).sum())],
    }
    if "rating_duration_seconds" in df.columns:
        secs = df["rating_duration_seconds"].dropna()
        if len(secs):
            rows["rating_seconds_median"] = [float(secs.median())]
            rows["rating_seconds_p95"]    = [float(secs.quantile(0.95))]
    save_table(pd.DataFrame(rows), tables_dir, "overview")

    if "model_name"     in df.columns: save_table(df.groupby("model_name").size().rename("n").reset_index(),     tables_dir, "n_by_model")
    if "context_level"  in df.columns: save_table(df.groupby("context_level").size().rename("n").reset_index(),  tables_dir, "n_by_context_level")
    if "anti_pattern_type" in df.columns: save_table(df.groupby("anti_pattern_type").size().rename("n").reset_index(), tables_dir, "n_by_anti_pattern")


def proportions_block(
    df: pd.DataFrame, group_col: str, preferred_order: list[str],
    tables_dir: Path, figures_dir: Path, *, rotate: bool = False,
) -> None:
    if group_col not in df.columns:
        warnings.warn(f"skipping proportions by {group_col}: column absent")
        return
    groups = _ordered_categories(df[group_col], preferred_order)
    for dim in ALL_DIMS:
        if dim not in df.columns:
            continue
        table = proportions_per_level(df, dim, group_col)
        if table.empty:
            continue
        table = table.set_index("group").reindex(groups).reset_index().rename(columns={"index": "group"})
        save_table(table, tables_dir, f"{dim}_by_{group_col}")

        fig = stacked_proportion_chart(table, dim, group_col, rotate=rotate)
        save_figure(fig, figures_dir, f"{dim}_by_{group_col}")


def hallucination_block(df: pd.DataFrame, tables_dir: Path, figures_dir: Path) -> None:
    if "hallucination_categories" not in df.columns:
        warnings.warn("hallucination: skipped (no hallucination_categories column)")
        return

    cats = HALLUCINATION_CATEGORIES
    rows: list[dict] = []
    n = len(df)
    for cat in cats:
        k = int(df["hallucination_categories"].apply(lambda s: cat in s).sum())
        lo, hi = wilson_ci(k, n)
        rows.append({"category": cat, "count": k, "rate": round(k / n if n else float("nan"), 4),
                     "ci_lo": round(lo, 4), "ci_hi": round(hi, 4)})
    table = pd.DataFrame(rows)
    save_table(table, tables_dir, "hallucination_overall")

    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.bar(table["category"], table["rate"])
    errs = [table["rate"] - table["ci_lo"], table["ci_hi"] - table["rate"]]
    ax.errorbar(table["category"], table["rate"], yerr=errs, fmt="none", capsize=4,
                ecolor="black", linewidth=1)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Rate (95% Wilson CI)")
    ax.set_title("Hallucination category rate (multi-label)")
    ax.tick_params(axis="x", labelrotation=30)
    save_figure(fig, figures_dir, "hallucination_overall")

    # Per (category × context_level) cell — for the chi-squared step in §4.6.
    if "context_level" in df.columns:
        per_ctx: list[dict] = []
        for ctx, gdf in df.groupby("context_level"):
            n_ctx = len(gdf)
            for cat in cats:
                k = int(gdf["hallucination_categories"].apply(lambda s: cat in s).sum())
                lo, hi = wilson_ci(k, n_ctx)
                per_ctx.append({"context_level": ctx, "category": cat,
                                "n_cell": n_ctx, "count": k,
                                "rate": round(k / n_ctx if n_ctx else float("nan"), 4),
                                "ci_lo": round(lo, 4), "ci_hi": round(hi, 4)})
        save_table(pd.DataFrame(per_ctx), tables_dir, "hallucination_by_context")


def quality_alignment_block(df: pd.DataFrame, tables_dir: Path, figures_dir: Path) -> None:
    cols = ["attributes_correctly_aligned", "incorrectly_mentioned_attributes"]
    if not all(c in df.columns for c in cols):
        warnings.warn(f"quality alignment: missing one of {cols} — skipped")
        return
    if "anti_pattern_type" not in df.columns:
        warnings.warn("quality alignment: no anti_pattern_type column — skipped")
        return

    agg = df.groupby("anti_pattern_type")[cols].agg(["mean", "std", "count"]).round(3)
    agg.columns = ["_".join(c) for c in agg.columns]
    save_table(agg.reset_index(), tables_dir, "quality_alignment_by_anti_pattern")

    # Mention rate per anti-pattern (any expected attribute mentioned at all).
    if "expected_quality_attributes" in df.columns and "llm_quality_attributes_mentioned" in df.columns:
        def _any_aligned(row) -> int:
            exp = set(_ensure_list(row.get("expected_quality_attributes")))
            men = set(_ensure_list(row.get("llm_quality_attributes_mentioned")))
            return 1 if (exp & men) else 0

        df = df.copy()
        df["_any_aligned"] = df.apply(_any_aligned, axis=1)
        per_ap = df.groupby("anti_pattern_type").agg(
            n=("_any_aligned", "count"),
            alignment_rate=("_any_aligned", "mean"),
        ).reset_index()
        save_table(per_ap, tables_dir, "alignment_rate_by_anti_pattern")


def h1_baseline_comparison(df: pd.DataFrame, tables_dir: Path) -> None:
    """
    H1: paired Cliff's δ between analyser-only and each hybrid context level,
    per dimension. Pairing is by (file_path, symbol_name, line) so the same
    instance is compared across conditions.
    """
    if "context_level" not in df.columns:
        warnings.warn("H1 comparison: no context_level column — skipped")
        return
    if "analyser_only" not in set(df["context_level"].dropna().astype(str)):
        warnings.warn("H1 comparison: no analyser_only rows in input — skipped")
        return

    df = df.copy()
    for dim in ALL_DIMS:
        if dim in df.columns:
            df[f"{dim}_num"] = df[dim].map(ORDINAL_NUM)

    instance_keys = ["file_path", "symbol_name", "line"]
    if not all(c in df.columns for c in instance_keys):
        warnings.warn("H1 comparison: missing instance keys — skipped")
        return

    baseline = df[df["context_level"] == "analyser_only"]
    other_levels = [c for c in CONTEXT_LEVEL_ORDER[1:] if c in df["context_level"].unique()]

    rows: list[dict] = []
    pvals_by_dim: dict[str, list[tuple[str, float]]] = {}  # for optional Holm

    for dim in ALL_DIMS:
        if f"{dim}_num" not in df.columns:
            continue
        for lvl in other_levels:
            hybrid = df[df["context_level"] == lvl]
            x = baseline[f"{dim}_num"].dropna().tolist()
            y = hybrid[f"{dim}_num"].dropna().tolist()
            delta, label = cliffs_delta(y, x)  # δ > 0 → hybrid > baseline
            rows.append({
                "dimension":    dim,
                "context_level": lvl,
                "n_baseline":   len(x),
                "n_hybrid":     len(y),
                "cliffs_delta": round(delta, 4),
                "magnitude":    label,
            })

    save_table(pd.DataFrame(rows), tables_dir, "h1_baseline_vs_hybrid_cliffs_delta")


def context_monotonicity_table(df: pd.DataFrame, tables_dir: Path) -> None:
    """
    H2a: monotonic improvement with context level. Reports, per dimension,
    the proportion of 'good' at each level — input to the CLMM fitted in R.
    """
    if "context_level" not in df.columns:
        return
    levels = [l for l in CONTEXT_LEVEL_ORDER if l in df["context_level"].unique()]
    rows: list[dict] = []
    for dim in ALL_DIMS:
        if dim not in df.columns:
            continue
        for lvl in levels:
            sub = df[df["context_level"] == lvl][dim].dropna()
            n = len(sub)
            for level in ORDINAL_VALUES:
                k = int((sub == level).sum())
                lo, hi = wilson_ci(k, n)
                rows.append({
                    "dimension":     dim,
                    "context_level": lvl,
                    "ordinal_level": level,
                    "n":             n,
                    "count":         k,
                    "proportion":    round(k / n if n else float("nan"), 4),
                    "ci_lo":         round(lo, 4),
                    "ci_hi":         round(hi, 4),
                })
    save_table(pd.DataFrame(rows), tables_dir, "context_monotonicity_long")


# ── LLM-only architecture arm (H1b + recall) ─────────────────────────────────

FRONTIER_MODEL = "gpt-5.4"


def llm_only_recall(df: pd.DataFrame, tables_dir: Path, figures_dir: Path) -> None:
    """
    LLM-only detection recall (§4.5.1): of the known instances, what fraction did the
    ungrounded LLM-only arm independently recover? Reported per anti-pattern with a
    Wilson 95% CI. Known set = distinct instances seen by the grounded arms.
    """
    if "architecture" not in df.columns or "instance_key" not in df.columns:
        warnings.warn("llm-only recall: missing architecture/instance_key — skipped")
        return
    if "llm_only" not in set(df["architecture"]):
        warnings.warn("llm-only recall: no llm_only rows — skipped")
        return

    # Known instances = those evaluated by the grounded arms (hybrid + analyser).
    grounded = df[df["architecture"] != "llm_only"]
    known = grounded[["anti_pattern_type", "instance_key"]].drop_duplicates()

    llm = df[df["architecture"] == "llm_only"]
    matched_keys = set(
        llm.loc[llm.get("is_spurious", False) != True, "matched_instance_id"].dropna()
    ) if "matched_instance_id" in llm.columns else set()

    rows: list[dict] = []
    for ap, grp in known.groupby("anti_pattern_type"):
        keys = set(grp["instance_key"])
        n = len(keys)
        recovered = len(keys & matched_keys)
        lo, hi = wilson_ci(recovered, n)
        rows.append({
            "anti_pattern_type": ap, "known": n, "recovered": recovered,
            "recall": round(recovered / n if n else float("nan"), 4),
            "ci_lo": round(lo, 4), "ci_hi": round(hi, 4),
        })
    # Overall row
    all_keys = set(known["instance_key"]); n = len(all_keys)
    rec = len(all_keys & matched_keys)
    lo, hi = wilson_ci(rec, n)
    rows.append({"anti_pattern_type": "ALL", "known": n, "recovered": rec,
                 "recall": round(rec / n if n else float("nan"), 4),
                 "ci_lo": round(lo, 4), "ci_hi": round(hi, 4)})

    table = pd.DataFrame(rows)
    save_table(table, tables_dir, "llm_only_recall")

    plot = table[table["anti_pattern_type"] != "ALL"]
    if not plot.empty:
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        ax.bar(plot["anti_pattern_type"], plot["recall"])
        errs = [plot["recall"] - plot["ci_lo"], plot["ci_hi"] - plot["recall"]]
        ax.errorbar(plot["anti_pattern_type"], plot["recall"], yerr=errs, fmt="none",
                    capsize=4, ecolor="black", linewidth=1)
        ax.set_ylim(0, 1)
        ax.set_ylabel("Recall (95% Wilson CI)")
        ax.set_title("LLM-only detection recall by anti-pattern")
        ax.tick_params(axis="x", labelrotation=20)
        save_figure(fig, figures_dir, "llm_only_recall")


def llm_only_spurious(df: pd.DataFrame, tables_dir: Path) -> None:
    """Spurious LLM-only detections (matched no known instance) — descriptive only (§4.5.1)."""
    if "architecture" not in df.columns:
        return
    llm = df[df["architecture"] == "llm_only"]
    if llm.empty or "is_spurious" not in llm.columns:
        return
    spurious = llm[llm["is_spurious"] == True]
    summary = pd.DataFrame([{
        "llm_only_findings": len(llm),
        "matched": int((llm["is_spurious"] == False).sum()),
        "spurious": len(spurious),
        "spurious_rate": round(len(spurious) / len(llm), 4) if len(llm) else float("nan"),
    }])
    save_table(summary, tables_dir, "llm_only_spurious_summary")

    if "hallucination_categories" in spurious.columns and not spurious.empty:
        rows = []
        for cat in HALLUCINATION_CATEGORIES:
            k = int(spurious["hallucination_categories"].apply(lambda s: cat in s).sum())
            rows.append({"category": cat, "count": k})
        save_table(pd.DataFrame(rows), tables_dir, "llm_only_spurious_hallucinations")


def h1b_hybrid_vs_llmonly(df: pd.DataFrame, tables_dir: Path) -> None:
    """
    H1b: hybrid (Minimal, frontier) vs LLM-only, frontier model, on the instances
    LLM-only recovered. Paired Cliff's δ per quality dimension (δ>0 → hybrid > LLM-only).
    """
    if "architecture" not in df.columns or "instance_key" not in df.columns:
        warnings.warn("H1b: missing architecture/instance_key — skipped")
        return
    if "llm_only" not in set(df["architecture"]):
        warnings.warn("H1b: no llm_only rows — skipped")
        return

    df = df.copy()
    for dim in ALL_DIMS:
        if dim in df.columns:
            df[f"{dim}_num"] = df[dim].map(ORDINAL_NUM)

    hybrid = df[(df["architecture"] == "hybrid") &
                (df["context_level"] == "minimal") &
                (df["model_name"] == FRONTIER_MODEL)]
    llm = df[(df["architecture"] == "llm_only") & (df.get("is_spurious", False) != True)]

    common = set(hybrid["instance_key"]) & set(llm["instance_key"])
    if not common:
        warnings.warn("H1b: no overlapping recovered instances — skipped")
        return

    rows: list[dict] = []
    for dim in ALL_DIMS:
        col = f"{dim}_num"
        if col not in df.columns:
            continue
        x = hybrid[hybrid["instance_key"].isin(common)][col].dropna().tolist()
        y = llm[llm["instance_key"].isin(common)][col].dropna().tolist()
        delta, label = cliffs_delta(x, y)  # δ>0 → hybrid > llm_only
        rows.append({
            "dimension": dim, "n_instances": len(common),
            "n_hybrid": len(x), "n_llm_only": len(y),
            "cliffs_delta": round(delta, 4), "magnitude": label,
        })
    save_table(pd.DataFrame(rows), tables_dir, "h1b_hybrid_vs_llmonly_cliffs_delta")


# ── Driver ───────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyse experiments.jsonl and emit thesis-ready tables and figures."
    )
    parser.add_argument("--input", "-i", required=True, type=Path,
                        help="Path to experiments.jsonl produced by score_runs.py")
    parser.add_argument("--output", "-o", default=Path("output"), type=Path,
                        help="Output root directory (default: ./output)")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"error: {args.input} not found", file=sys.stderr); return 2

    warnings.simplefilter("always")
    figures_dir = args.output / "figures"
    tables_dir  = args.output / "tables"

    df = clean(load(args.input))
    print(f"loaded {len(df)} row(s), {len(df.columns)} columns from {args.input}")

    overview(df, tables_dir)

    # Per-dimension stacked proportions (matches the thesis tables). A single frontier model
    # is used (§5.2.2), so there is no by-model grouping — the cross-model breakdown is removed.
    proportions_block(df, "context_level",    CONTEXT_LEVEL_ORDER, tables_dir, figures_dir, rotate=False)
    proportions_block(df, "anti_pattern_type", [],                 tables_dir, figures_dir, rotate=True)

    # Hallucinations.
    hallucination_block(df, tables_dir, figures_dir)

    # Quality-attribute alignment (counts + mention rate).
    quality_alignment_block(df, tables_dir, figures_dir)

    # H1a: analyser-only vs hybrid (per context level) — Cliff's δ. The 'minimal'
    # row is the headline H1a contrast; the others are the robustness sweep.
    h1_baseline_comparison(df, tables_dir)

    # H1b: hybrid (Minimal, frontier) vs LLM-only on recovered instances.
    h1b_hybrid_vs_llmonly(df, tables_dir)

    # LLM-only detection recall + spurious-detection characterisation.
    llm_only_recall(df, tables_dir, figures_dir)
    llm_only_spurious(df, tables_dir)

    # Long-format proportions for the CLMM in R.
    context_monotonicity_table(df, tables_dir)

    print(f"\ndone — tables in {tables_dir.resolve()}")
    print(f"       figures in {figures_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
