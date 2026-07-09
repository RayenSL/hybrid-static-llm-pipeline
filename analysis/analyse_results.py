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

# Verified-repair ladder (ascending; `resolved` is the only success). Hybrid context
# levels in order for the H2b trend.
LADDER_ORDER = ["unapplicable", "build_fails", "builds_unresolved", "resolved"]
HYBRID_CONTEXT_ORDER = ["minimal", "structural", "relational", "full"]

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

    # Derive architecture if absent (older rows): analyser_only / hybrid / agentic.
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
    for col in ("context_truncated", "refusal_detected"):
        if col in df.columns:
            df[col] = df[col].map(_to_bool)

    # is_spurious is TRI-STATE and MUST stay so: agentic detection-finding rows carry true/false, while
    # agentic verified-repair rows (and hybrid/analyser rows) carry null. The agentic analysis separates
    # finding rows (non-null) from verified-repair rows (null) on exactly this signal — collapsing null→False
    # would silently fold verified-repair rows into the detection set and corrupt recall/precision + Table 5.5.
    if "is_spurious" in df.columns:
        df["is_spurious"] = df["is_spurious"].map(_to_bool_or_na)

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


def _to_bool_or_na(v):
    """Like _to_bool but PRESERVES null as NaN (float) rather than collapsing it to False — used for the
    tri-state is_spurious column. NaN keeps .notna()/==True/==False behaving correctly and, unlike pd.NA,
    is safe inside boolean masks."""
    if v is None: return float("nan")
    if isinstance(v, float) and math.isnan(v): return float("nan")
    return _to_bool(v)


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


# ── Agentic architecture arm (H1b + recall) ──────────────────────────────────
#
# The agentic run trace carries TWO row types, both architecture == "agentic":
#   • finding rows      — is_spurious is non-null (True/False); feed recall + precision and the
#                         H1b explanation rubric;
#   • verified-repair rows — verified_repair_ladder is non-null, is_spurious is null; feed Table 5.3.
# The helpers below restrict to finding rows so verified rows never inflate detection counts.

FRONTIER_MODEL = "gpt-5.4"


def _agentic_findings(df: pd.DataFrame) -> pd.DataFrame:
    """Agentic detection finding rows only (excludes the per-instance verified-repair rows)."""
    a = df[df["architecture"] == "agentic"]
    return a[a["is_spurious"].notna()] if "is_spurious" in a.columns else a.iloc[0:0]


def agentic_recall(df: pd.DataFrame, tables_dir: Path, figures_dir: Path) -> None:
    """
    Agentic detection recall (§4.5.1, Table 5.6): of the known instances, what fraction did the
    ungrounded agentic arm independently recover from the unannotated file? Reported per anti-pattern
    with a Wilson 95% CI. Known set = distinct instances seen by the grounded arms.
    """
    if "architecture" not in df.columns or "instance_key" not in df.columns:
        warnings.warn("agentic recall: missing architecture/instance_key — skipped")
        return
    if "agentic" not in set(df["architecture"]):
        warnings.warn("agentic recall: no agentic rows — skipped")
        return

    # Known instances = those evaluated by the grounded arms (hybrid + analyser).
    grounded = df[df["architecture"] != "agentic"]
    known = grounded[["anti_pattern_type", "instance_key"]].drop_duplicates()

    findings = _agentic_findings(df)
    matched_keys = set(
        findings.loc[findings["is_spurious"] == False, "matched_instance_id"].dropna()
    ) if "matched_instance_id" in findings.columns else set()
    n_reported_matches = int((findings["is_spurious"] == False).sum()) if "is_spurious" in findings.columns else 0

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
    # Guard against a silent zero: if the arm reported matches but none intersect the known instance_key
    # set, matched_instance_id and instance_key are in different string spaces (usually a file_path format
    # mismatch between the agentic --from trace and the hybrid/analyser traces), not a true 0% recall.
    if n_reported_matches > 0 and rec == 0:
        warnings.warn(
            f"agentic recall: {n_reported_matches} matched finding(s) reported but none intersect the "
            "known instance_key set — matched_instance_id and instance_key likely differ in format "
            "(e.g. file_path normalisation). Recall shown as 0; verify path consistency before trusting it.")
    lo, hi = wilson_ci(rec, n)
    rows.append({"anti_pattern_type": "ALL", "known": n, "recovered": rec,
                 "recall": round(rec / n if n else float("nan"), 4),
                 "ci_lo": round(lo, 4), "ci_hi": round(hi, 4)})

    table = pd.DataFrame(rows)
    save_table(table, tables_dir, "agentic_recall")

    plot = table[table["anti_pattern_type"] != "ALL"]
    if not plot.empty:
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        ax.bar(plot["anti_pattern_type"], plot["recall"])
        errs = [plot["recall"] - plot["ci_lo"], plot["ci_hi"] - plot["recall"]]
        ax.errorbar(plot["anti_pattern_type"], plot["recall"], yerr=errs, fmt="none",
                    capsize=4, ecolor="black", linewidth=1)
        ax.set_ylim(0, 1)
        ax.set_ylabel("Recall (95% Wilson CI)")
        ax.set_title("Agentic detection recall by anti-pattern")
        ax.tick_params(axis="x", labelrotation=20)
        save_figure(fig, figures_dir, "agentic_recall")


def agentic_spurious(df: pd.DataFrame, tables_dir: Path) -> None:
    """Spurious agentic detections (matched no known instance) — precision evidence, descriptive (§4.5.1)."""
    if "architecture" not in df.columns:
        return
    findings = _agentic_findings(df)
    if findings.empty or "is_spurious" not in findings.columns:
        return
    spurious = findings[findings["is_spurious"] == True]
    summary = pd.DataFrame([{
        "agentic_findings": len(findings),
        "matched": int((findings["is_spurious"] == False).sum()),
        "spurious": len(spurious),
        "spurious_rate": round(len(spurious) / len(findings), 4) if len(findings) else float("nan"),
    }])
    save_table(summary, tables_dir, "agentic_spurious_summary")

    if "hallucination_categories" in spurious.columns and not spurious.empty:
        rows = []
        for cat in HALLUCINATION_CATEGORIES:
            k = int(spurious["hallucination_categories"].apply(lambda s: cat in s).sum())
            rows.append({"category": cat, "count": k})
        save_table(pd.DataFrame(rows), tables_dir, "agentic_spurious_hallucinations")


def h1b_hybrid_vs_agentic(df: pd.DataFrame, tables_dir: Path) -> None:
    """
    H1b (Table 5.5): hybrid (Minimal, frontier) vs agentic, frontier model, on the instances the
    agentic arm recovered (matched finding rows only). Paired Cliff's δ per quality dimension
    (δ>0 → hybrid > agentic).
    """
    if "architecture" not in df.columns or "instance_key" not in df.columns:
        warnings.warn("H1b: missing architecture/instance_key — skipped")
        return
    if "agentic" not in set(df["architecture"]):
        warnings.warn("H1b: no agentic rows — skipped")
        return

    df = df.copy()
    for dim in ALL_DIMS:
        if dim in df.columns:
            df[f"{dim}_num"] = df[dim].map(ORDINAL_NUM)

    hybrid = df[(df["architecture"] == "hybrid") &
                (df["context_level"] == "minimal") &
                (df["model_name"] == FRONTIER_MODEL)]
    # Recovered instances only: matched agentic finding rows (is_spurious == False excludes both
    # spurious findings and the per-instance verified-repair rows, which carry is_spurious == null).
    agentic = df[(df["architecture"] == "agentic") & (df.get("is_spurious", False) == False)]

    common = set(hybrid["instance_key"]) & set(agentic["instance_key"])
    if not common:
        warnings.warn("H1b: no overlapping recovered instances — skipped")
        return

    rows: list[dict] = []
    for dim in ALL_DIMS:
        col = f"{dim}_num"
        if col not in df.columns:
            continue
        x = hybrid[hybrid["instance_key"].isin(common)][col].dropna().tolist()
        y = agentic[agentic["instance_key"].isin(common)][col].dropna().tolist()
        delta, label = cliffs_delta(x, y)  # δ>0 → hybrid > agentic
        rows.append({
            "dimension": dim, "n_instances": len(common),
            "n_hybrid": len(x), "n_agentic": len(y),
            "cliffs_delta": round(delta, 4), "magnitude": label,
        })
    save_table(pd.DataFrame(rows), tables_dir, "h1b_hybrid_vs_agentic_cliffs_delta")


# ── Verified-repair (objective repair outcome, §4.5.1 / Tables 5.3 & 5.7) ─────

def load_verified(pattern: str) -> pd.DataFrame:
    """Load + clean the verify-repair JSONL(s). Accepts a path or glob. Keeps only rows
    carrying a verified-repair verdict and normalises the ladder + binary success."""
    import glob as _glob
    paths = sorted(_glob.glob(pattern)) or ([pattern] if Path(pattern).exists() else [])
    frames = [load(Path(p)) for p in paths]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    df = clean(pd.concat(frames, ignore_index=True))
    if "verified_repair_ladder" not in df.columns:
        return pd.DataFrame()
    df = df[df["verified_repair_ladder"].notna()].copy()
    df["verified_repair_ladder"] = df["verified_repair_ladder"].astype(str).str.strip().str.lower()
    df["verified_repair_success"] = (
        df["verified_repair_success"].map(_to_bool) if "verified_repair_success" in df.columns else False
    )
    # Normalise the iterative-arm snapshot tag ("first_build" | "final"); NA on hybrid/analyser rows and
    # on any older agentic rows written before the snapshot split. Used by the §4.4.1 2×2 (Table 5.7).
    if "agentic_snapshot" in df.columns:
        df["agentic_snapshot"] = df["agentic_snapshot"].astype("string").str.strip().str.lower()
        df.loc[~df["agentic_snapshot"].isin(["first_build", "final"]), "agentic_snapshot"] = pd.NA
    return df


def _ladder_counts(sub: pd.DataFrame) -> dict:
    col = sub["verified_repair_ladder"] if "verified_repair_ladder" in sub.columns else pd.Series(dtype=str)
    return {lvl: int((col == lvl).sum()) for lvl in LADDER_ORDER}


def _final_only(df: pd.DataFrame) -> pd.DataFrame:
    """Keep exactly one verified-repair row per instance for the iterative arms by dropping their
    first_build snapshot rows (the deployed outcome is the 'final' state). Hybrid/analyser rows carry no
    snapshot (NA) and pass through unchanged. Prevents the two snapshots from double-counting in the
    architecture contrast (Table 5.3) and its McNemar (§4.4.1)."""
    if "agentic_snapshot" not in df.columns:
        return df
    s = df["agentic_snapshot"]
    return df[s.isna() | (s == "final")]


def verified_repair_by_architecture(df: pd.DataFrame, tables_dir: Path) -> None:
    """Table 5.3: verified-repair success by architecture at Minimal context (frontier model),
    with the ordinal-ladder breakdown. Analyser-only emits no repair → 0 by construction. The agentic
    arm is scored on its final edited solution (no separate applier). McNemar contrasts the paired
    hybrid-vs-agentic binary outcome (H1b); the agentic_recovered column allows restricting that
    contrast to instances both arms recovered, per the §4.4.1 H1b objective-repair register."""
    contrast = df[(df["model_name"] == FRONTIER_MODEL) & (df["context_level"] == "minimal")]
    rows = []
    for arch in ("analyser_only", "hybrid", "agentic"):
        # The agentic arm now emits two snapshots per instance; score its deployed 'final' state here.
        adf = _final_only(contrast[contrast["architecture"] == arch])
        n = len(adf)
        k = int(adf["verified_repair_success"].sum()) if n else 0
        lo, hi = wilson_ci(k, n)
        rows.append({
            "architecture": arch,
            "n": n,
            "resolved": k,
            "success_pct": round(100 * k / n, 2) if n else 0.0,
            "ci_lo_pct": round(100 * lo, 2) if n else float("nan"),
            "ci_hi_pct": round(100 * hi, 2) if n else float("nan"),
            **_ladder_counts(adf),
            "note": "no repair (0 by construction)" if arch == "analyser_only" else "",
        })
    save_table(pd.DataFrame(rows), tables_dir, "verified_repair_by_architecture")
    save_table(mcnemar_paired(_final_only(contrast), "hybrid", "agentic"),
               tables_dir, "verified_repair_mcnemar_hybrid_vs_agentic")


def mcnemar_paired(df: pd.DataFrame, arch_a: str, arch_b: str) -> pd.DataFrame:
    """McNemar on the paired binary verified-repair outcome of two architectures, matched per
    instance_key. Exact binomial on the discordant pairs when they are few; continuity-corrected
    chi-square otherwise."""
    if "instance_key" not in df.columns:
        return pd.DataFrame([{"arch_a": arch_a, "arch_b": arch_b, "note": "no instance_key column"}])
    a = df[df["architecture"] == arch_a].groupby("instance_key")["verified_repair_success"].max()
    b = df[df["architecture"] == arch_b].groupby("instance_key")["verified_repair_success"].max()
    paired = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna().astype(bool)
    a_yes_b_no = int((paired["a"] & ~paired["b"]).sum())
    a_no_b_yes = int((~paired["a"] & paired["b"]).sum())
    stat, p = _mcnemar_stat(a_yes_b_no, a_no_b_yes)
    return pd.DataFrame([{
        "arch_a": arch_a, "arch_b": arch_b, "n_pairs": len(paired),
        "a_yes_b_no": a_yes_b_no, "a_no_b_yes": a_no_b_yes,
        "statistic": None if stat != stat else round(stat, 4),
        "p_value":   None if p != p else round(p, 4),
    }])


def _mcnemar_stat(b: int, c: int) -> tuple[float, float]:
    n = b + c
    if n == 0:
        return (float("nan"), float("nan"))
    if n < 25:  # exact binomial on the discordant pairs
        from scipy.stats import binomtest
        return (float(min(b, c)), float(binomtest(min(b, c), n, 0.5).pvalue))
    from scipy.stats import chi2
    stat = (abs(b - c) - 1) ** 2 / n  # continuity-corrected
    return (float(stat), float(1 - chi2.cdf(stat, 1)))


def verified_repair_by_context(df: pd.DataFrame, tables_dir: Path) -> None:
    """Table 5.10 (H2b): verified-repair success by context level (hybrid arm, frontier model), with a
    Cochran–Armitage trend test and a long-format CSV (one row per generation) for the binomial
    GLMM fitted in R. The §4.4.1 2×2 (Table 5.7) is a separate architecture contrast, not this one."""
    sub = df[(df["architecture"] == "hybrid") & (df["model_name"] == FRONTIER_MODEL)]
    rows, long_rows = [], []
    for ord_i, lvl in enumerate(HYBRID_CONTEXT_ORDER):
        ldf = sub[sub["context_level"] == lvl]
        n = len(ldf)
        k = int(ldf["verified_repair_success"].sum()) if n else 0
        lo, hi = wilson_ci(k, n)
        rows.append({
            "context_level": lvl, "context_ord": ord_i, "n": n, "resolved": k,
            "success_pct": round(100 * k / n, 2) if n else float("nan"),
            "ci_lo_pct": round(100 * lo, 2) if n else float("nan"),
            "ci_hi_pct": round(100 * hi, 2) if n else float("nan"),
        })
        for _, r in ldf.iterrows():
            long_rows.append({
                "instance_key": r.get("instance_key"),
                "context_level": lvl, "context_ord": ord_i,
                "verified_repair_success": int(bool(r["verified_repair_success"])),
            })
    by_ctx = pd.DataFrame(rows)
    save_table(by_ctx, tables_dir, "verified_repair_by_context")
    save_table(pd.DataFrame(long_rows), tables_dir, "verified_repair_context_long")
    save_table(cochran_armitage(by_ctx), tables_dir, "verified_repair_context_trend")


def cochran_armitage(by_ctx: pd.DataFrame) -> pd.DataFrame:
    """Cochran–Armitage linear-trend test on the resolved proportion across the ordered context
    levels (scores = ordinal index). A simpler corroborating check for the R GLMM (H2b)."""
    valid = by_ctx[by_ctx["n"] > 0]
    if len(valid) < 2:
        return pd.DataFrame([{"test": "cochran_armitage", "z": float("nan"),
                              "p_value": float("nan"), "groups": len(valid),
                              "note": "need >=2 non-empty levels"}])
    t   = valid["context_ord"].to_numpy(dtype=float)
    n_i = valid["n"].to_numpy(dtype=float)
    x_i = valid["resolved"].to_numpy(dtype=float)
    N = n_i.sum()
    p_bar = x_i.sum() / N
    t_bar = (n_i * t).sum() / N
    num = (x_i * (t - t_bar)).sum()
    var = p_bar * (1 - p_bar) * (n_i * (t - t_bar) ** 2).sum()
    if var <= 0:
        return pd.DataFrame([{"test": "cochran_armitage", "z": float("nan"),
                              "p_value": float("nan"), "groups": len(valid),
                              "note": "degenerate (zero variance)"}])
    from scipy.stats import norm
    z = num / math.sqrt(var)
    p = 2 * (1 - norm.cdf(abs(z)))
    return pd.DataFrame([{"test": "cochran_armitage", "z": round(z, 4),
                          "p_value": round(p, 4), "groups": len(valid), "note": ""}])


# ── Grounding × control-structure 2×2 (H1c, §4.4.1, Tables 5.7–5.9) ───────────

def _success_by_instance(df: pd.DataFrame, arch: str, snapshot: str | None) -> pd.Series:
    """instance_key → resolved-in-any-run (bool) for one architecture and (optional) snapshot. Mirrors
    the per-instance .max() collapse used by mcnemar_paired so all paired contrasts share one convention."""
    sub = df[df["architecture"] == arch]
    if snapshot is not None and "agentic_snapshot" in sub.columns:
        sub = sub[sub["agentic_snapshot"] == snapshot]
    if sub.empty or "instance_key" not in sub.columns:
        return pd.Series(dtype=bool)
    return sub.groupby("instance_key")["verified_repair_success"].max().astype(bool)


def newcombe_paired_ci(a11: int, a10: int, a01: int, a00: int, alpha: float = 0.05):
    """Newcombe's method-10 CI for the difference of two PAIRED proportions — the Wilson-based interval
    the thesis specifies for the paired verified-repair risk difference (§4.6). Cells: a11 both-resolved,
    a10 A-only, a01 B-only, a00 neither. Returns (diff = pA − pB, lo, hi)."""
    n = a11 + a10 + a01 + a00
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    p1 = (a11 + a10) / n
    p2 = (a11 + a01) / n
    diff = p1 - p2
    l1, u1 = wilson_ci(a11 + a10, n)
    l2, u2 = wilson_ci(a11 + a01, n)
    denom = (a11 + a10) * (a01 + a00) * (a11 + a01) * (a10 + a00)
    if denom <= 0:
        phi = 0.0
    else:
        A = a11 * a00 - a10 * a01
        phi = (A - n / 2) / math.sqrt(denom) if A > n / 2 else (0.0 if A >= 0 else A / math.sqrt(denom))
    lo = diff - math.sqrt(max(0.0, (p1 - l1) ** 2 - 2 * phi * (p1 - l1) * (u2 - p2) + (u2 - p2) ** 2))
    hi = diff + math.sqrt(max(0.0, (u1 - p1) ** 2 - 2 * phi * (u1 - p1) * (p2 - l2) + (p2 - l2) ** 2))
    return (diff, lo, hi)


def _paired_contrast(a: pd.Series, b: pd.Series, label: str, isolates: str) -> dict:
    """Paired 2×2 of two success-by-instance series → risk difference (Newcombe/Wilson CI) + McNemar p."""
    paired = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna().astype(bool)
    a11 = int(( paired.a &  paired.b).sum())
    a10 = int(( paired.a & ~paired.b).sum())
    a01 = int((~paired.a &  paired.b).sum())
    a00 = int((~paired.a & ~paired.b).sum())
    diff, lo, hi = newcombe_paired_ci(a11, a10, a01, a00)
    _, p = _mcnemar_stat(a10, a01)
    _r = lambda v: None if v != v else round(v, 4)
    return {
        "contrast": label, "isolates": isolates, "n_pairs": len(paired),
        "a_yes_b_no": a10, "a_no_b_yes": a01,
        "risk_diff": _r(diff), "ci_lo": _r(lo), "ci_hi": _r(hi), "mcnemar_p": _r(p),
    }


def _holm_on_grounding(table: pd.DataFrame) -> pd.DataFrame:
    """Holm-correct the McNemar p-values of the GROUNDING contrasts within a family (§4.6). The iteration
    contrasts are net changes between two snapshots of one trajectory — not exchangeability tests — so they
    are excluded from the correction, matching the thesis's treatment."""
    if table.empty:
        return table
    mask = table["isolates"].str.startswith("grounding")
    ps = [v for v in table.loc[mask, "mcnemar_p"].tolist()]
    if ps and any(v is not None for v in ps):
        corrected = holm_correct([v if v is not None else 1.0 for v in ps])
        table.loc[mask, "mcnemar_p_holm"] = [round(c, 4) for c in corrected]
    return table


def verified_repair_2x2(df: pd.DataFrame, tables_dir: Path) -> None:
    """
    Table 5.7 (the 2×2 of grounding × control structure) + Table 5.8 (single-factor contrasts from it) +
    Table 5.9 (H1b-family: single-shot grounding and ungrounded iteration), all §4.4.1 at Minimal grounding
    on the frontier model. The four cells are the TWO iterative arms — grounded_iterative and (ungrounded)
    agentic — each observed at its first_build (single-pass) and final (iterative) snapshot. The hybrid arm
    is reported beneath as the deployed single-pass grounded comparator; it is NOT a cell of the square.
    H1c is the grounded-vs-ungrounded contrast at the iterative snapshot, which varies grounding alone.
    """
    if "agentic_snapshot" not in df.columns:
        warnings.warn("2×2: no agentic_snapshot column (run the agentic/grounded arms) — skipped")
        return
    base = df[(df["model_name"] == FRONTIER_MODEL) & (df["context_level"] == "minimal")]
    present = set(base["architecture"])
    if "agentic" not in present:
        warnings.warn("2×2: no agentic rows — skipped")
        return
    grounded_present = "grounded_iterative" in present
    if not grounded_present:
        warnings.warn("2×2: no grounded_iterative rows — H1c/grounding contrasts unavailable; "
                      "reporting the ungrounded row + iteration contrast only")

    # ── Table 5.7: the four cells (+ hybrid comparator beneath) ──────────────
    cells = []
    for arm_label, arch in (("grounded", "grounded_iterative"), ("ungrounded", "agentic")):
        if arch not in present:
            continue
        for snap in ("first_build", "final"):
            sub = base[(base["architecture"] == arch) & (base["agentic_snapshot"] == snap)]
            n = len(sub)
            k = int(sub["verified_repair_success"].sum()) if n else 0
            lo, hi = wilson_ci(k, n) if n else (float("nan"), float("nan"))
            cells.append({
                "arm": arm_label, "architecture": arch, "snapshot": snap,
                "control_structure": "single_pass" if snap == "first_build" else "iterative",
                "n": n, "resolved": k,
                "success_pct": round(100 * k / n, 2) if n else float("nan"),
                "ci_lo_pct": round(100 * lo, 2) if n else float("nan"),
                "ci_hi_pct": round(100 * hi, 2) if n else float("nan"),
            })
    hyb = base[base["architecture"] == "hybrid"]
    if len(hyb):
        n = len(hyb); k = int(hyb["verified_repair_success"].sum()); lo, hi = wilson_ci(k, n)
        cells.append({
            "arm": "comparator", "architecture": "hybrid", "snapshot": "applied_literally",
            "control_structure": "single_pass", "n": n, "resolved": k,
            "success_pct": round(100 * k / n, 2), "ci_lo_pct": round(100 * lo, 2),
            "ci_hi_pct": round(100 * hi, 2),
        })
    save_table(pd.DataFrame(cells), tables_dir, "verified_repair_2x2")

    # Per-instance success series feeding the paired contrasts.
    g_final = _success_by_instance(base, "grounded_iterative", "final")
    g_first = _success_by_instance(base, "grounded_iterative", "first_build")
    a_final = _success_by_instance(base, "agentic",            "final")
    a_first = _success_by_instance(base, "agentic",            "first_build")
    hyb_succ = _success_by_instance(base, "hybrid", None)

    # ── Table 5.8: single-factor contrasts drawn from the 2×2 ────────────────
    contrasts: list[dict] = []
    if grounded_present:
        contrasts.append(_paired_contrast(g_final, a_final, "grounded_vs_ungrounded_iterative_H1c", "grounding @ iterative"))
        contrasts.append(_paired_contrast(g_first, a_first, "grounded_vs_ungrounded_single_pass",   "grounding @ single-pass"))
        contrasts.append(_paired_contrast(g_final, g_first, "grounded_final_vs_first_build",         "iteration @ grounded"))
    contrasts.append(_paired_contrast(a_final, a_first, "ungrounded_final_vs_first_build", "iteration @ ungrounded"))
    if grounded_present:
        # Difference of grounding effects (descriptive interaction): effect@iterative − effect@single-pass.
        rate = lambda s: float(s.mean()) if len(s) else float("nan")
        eff_iter   = rate(g_final) - rate(a_final)
        eff_single = rate(g_first) - rate(a_first)
        inter = eff_iter - eff_single
        contrasts.append({
            "contrast": "difference_of_grounding_effects", "isolates": "interaction (descriptive)",
            "n_pairs": None, "a_yes_b_no": None, "a_no_b_yes": None,
            "risk_diff": None if inter != inter else round(inter, 4),
            "ci_lo": None, "ci_hi": None, "mcnemar_p": None,
        })
    save_table(_holm_on_grounding(pd.DataFrame(contrasts)), tables_dir, "verified_repair_2x2_contrasts")

    # ── Table 5.9: H1b family — single-shot grounding + ungrounded iteration ──
    h1b: list[dict] = []
    if len(hyb_succ):
        h1b.append(_paired_contrast(hyb_succ, a_first, "hybrid_vs_agentic_first_build", "grounding @ single-shot"))
    h1b.append(_paired_contrast(a_final, a_first, "agentic_final_vs_first_build", "iteration @ ungrounded"))
    save_table(_holm_on_grounding(pd.DataFrame(h1b)), tables_dir, "verified_repair_h1b_family_contrasts")


# ── Whole-solution quality impact (§ quality-impact) ──────────────────────────

def _qnum(v, default: int = 0):
    """Coerce a JSON delta value to a number; None/NaN/missing → default."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)) and not (isinstance(v, float) and np.isnan(v)):
        return v
    return default


def _quality_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Verified-repair rows carrying a quality_delta object, flattened to scalar columns. The iterative
    arms are restricted to their 'final' snapshot (the deployed state), matching the other verified tables.
    Empty when the run was produced without --quality-diff (no quality_delta column / all null)."""
    if "quality_delta" not in df.columns:
        return pd.DataFrame()
    d = _final_only(df).copy()
    d = d[d["quality_delta"].apply(lambda v: isinstance(v, dict))].copy()
    if d.empty:
        return pd.DataFrame()
    q = d["quality_delta"]
    d["q_smell_total"]       = q.apply(lambda v: _qnum(v.get("smell_total_delta")))
    d["q_smell_collateral"]  = q.apply(lambda v: bool(v.get("smell_collateral")))
    d["q_ca_available"]      = q.apply(lambda v: bool(v.get("ca_available")))
    d["q_ca_headline_total"] = q.apply(lambda v: _qnum(v.get("ca_headline_total_delta")))
    d["q_ca_all_total"]      = q.apply(lambda v: _qnum(v.get("ca_all_total_delta")))
    d["q_obsolete_total"]    = q.apply(lambda v: _qnum(v.get("compiler_obsolete_delta")))
    d["q_ca_introduced_n"]   = q.apply(lambda v: len(v.get("ca_introduced") or []))
    d["q_ca_removed_n"]      = q.apply(lambda v: len(v.get("ca_removed") or []))
    return d


def _quality_summary_row(prefix: dict, a: pd.DataFrame) -> dict:
    """One summary row: Layer-1 smell delta + collateral rate, and Layer-2 CA delta (over the CA-available
    subset). Positive deltas mean the repair ADDED problems (worse); negative means it removed them."""
    n = len(a)
    ca = a[a["q_ca_available"]]
    n_ca = len(ca)
    return {
        **prefix,
        "n_built": n,
        # Layer 1 (self-scored detector, whole solution)
        "smell_delta_mean": round(float(a["q_smell_total"].mean()), 3) if n else float("nan"),
        "smell_delta_sum": int(a["q_smell_total"].sum()) if n else 0,
        "collateral_n": int(a["q_smell_collateral"].sum()) if n else 0,
        "collateral_pct": round(100 * float(a["q_smell_collateral"].mean()), 1) if n else 0.0,
        # Layer 2 (independent CA instrument) — headline tier
        "n_ca_available": n_ca,
        "ca_headline_delta_mean": round(float(ca["q_ca_headline_total"].mean()), 3) if n_ca else float("nan"),
        "ca_headline_worse_n": int((ca["q_ca_headline_total"] > 0).sum()) if n_ca else 0,
        "ca_headline_better_n": int((ca["q_ca_headline_total"] < 0).sum()) if n_ca else 0,
        "ca_headline_neutral_n": int((ca["q_ca_headline_total"] == 0).sum()) if n_ca else 0,
        # Layer 2 — all tier (sensitivity) + set churn + obsolete corroboration
        "ca_all_delta_mean": round(float(ca["q_ca_all_total"].mean()), 3) if n_ca else float("nan"),
        "ca_introduced_mean": round(float(ca["q_ca_introduced_n"].mean()), 2) if n_ca else float("nan"),
        "ca_removed_mean": round(float(ca["q_ca_removed_n"].mean()), 2) if n_ca else float("nan"),
        "obsolete_delta_sum": int(ca["q_obsolete_total"].sum()) if n_ca else 0,
    }


def quality_impact_block(df: pd.DataFrame, tables_dir: Path) -> None:
    """Whole-solution quality impact of the applied repairs (the supervisor's question: do the changes
    improve or degrade the codebase, not just resolve the one flagged metric?). Three tables:
      • by architecture (Minimal, frontier) — the deployed state of each arm;
      • hybrid by context level — the context sweep parallel to H2b;
      • CA headline delta by category — WHERE any degradation/improvement lands.
    Only rows whose applied state built carry a quality_delta, so n_built ≤ the arm's resolved+unresolved."""
    q = _quality_rows(df)
    if q.empty:
        return

    have_dims = has(q, "model_name", "context_level", "architecture")
    base = q[(q["model_name"] == FRONTIER_MODEL) & (q["context_level"] == "minimal")] if have_dims else q

    # Table 1 — by architecture (deployed state, Minimal context / frontier model).
    rows = [_quality_summary_row({"architecture": arch}, base[base["architecture"] == arch])
            for arch in sorted(base["architecture"].dropna().unique())]
    if rows:
        save_table(pd.DataFrame(rows), tables_dir, "quality_impact_by_architecture")

    # Table 2 — hybrid by context level (parallels the H2b context sweep).
    if have_dims:
        hyb = q[(q["architecture"] == "hybrid") & (q["model_name"] == FRONTIER_MODEL)]
        ctx_rows = [_quality_summary_row({"context_level": ctx}, hyb[hyb["context_level"] == ctx])
                    for ctx in HYBRID_CONTEXT_ORDER if len(hyb[hyb["context_level"] == ctx])]
        if ctx_rows:
            save_table(pd.DataFrame(ctx_rows), tables_dir, "quality_impact_hybrid_by_context")

    # Table 3 — CA headline net delta by category, per architecture (net over the Minimal/frontier base).
    cat_rows = []
    for arch in sorted(base["architecture"].dropna().unique()):
        agg: dict[str, float] = {}
        for v in base[base["architecture"] == arch]["quality_delta"]:
            for cat, nn in (v.get("ca_headline_delta_by_category") or {}).items():
                agg[cat] = agg.get(cat, 0) + _qnum(nn)
        for cat, nn in sorted(agg.items(), key=lambda kv: (-abs(kv[1]), kv[0])):
            if nn != 0:
                cat_rows.append({"architecture": arch, "category": cat, "net_headline_delta": int(nn)})
    if cat_rows:
        save_table(pd.DataFrame(cat_rows), tables_dir, "quality_impact_ca_by_category")

    print(f"quality-impact: {len(q)} built row(s) carried a quality delta "
          f"({int(q['q_ca_available'].sum())} with CA data); wrote quality_impact_* tables")


# ── Driver ───────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyse experiments.jsonl and emit thesis-ready tables and figures."
    )
    parser.add_argument("--input", "-i", required=True, type=Path,
                        help="Path to experiments.jsonl produced by score_runs.py")
    parser.add_argument("--output", "-o", default=Path("output"), type=Path,
                        help="Output root directory (default: ./output)")
    parser.add_argument("--verified", type=str, default=None,
                        help="Path or glob to verify-repair JSONL(s); enables the verified-repair "
                             "tables (5.3 by architecture, 5.7 by context level) and, when the run used "
                             "--quality-diff, the whole-solution quality-impact tables.")
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

    # H1b: hybrid (Minimal, frontier) vs agentic on recovered instances.
    h1b_hybrid_vs_agentic(df, tables_dir)

    # Agentic detection recall + spurious-detection (precision) characterisation.
    agentic_recall(df, tables_dir, figures_dir)
    agentic_spurious(df, tables_dir)

    # Long-format proportions for the CLMM in R.
    context_monotonicity_table(df, tables_dir)

    # Verified-repair outcomes (objective; Tables 5.3 & 5.7). Optional second input.
    if args.verified:
        vdf = load_verified(args.verified)
        if vdf.empty:
            print(f"warning: no verified-repair rows matched {args.verified}", file=sys.stderr)
        else:
            print(f"loaded {len(vdf)} verified-repair row(s) from {args.verified}")
            verified_repair_by_architecture(vdf, tables_dir)
            verified_repair_by_context(vdf, tables_dir)
            verified_repair_2x2(vdf, tables_dir)
            # Whole-solution quality impact (only present when the run used --quality-diff).
            quality_impact_block(vdf, tables_dir)

    print(f"\ndone — tables in {tables_dir.resolve()}")
    print(f"       figures in {figures_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
