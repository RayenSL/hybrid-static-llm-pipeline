"""
Thesis evaluation analyser for the HybridLens experiments.

Loads a curated experiments file (JSONL or CSV) where each row is one scored
LLM run and produces:
  - descriptive statistics tables (CSV)
  - matplotlib figures (PNG)

Inputs columns expected (any subset is tolerated — missing columns are skipped
with a warning so the script never crashes on partial data):

  Identity:        experiment_id, instance_id, anti_pattern_type,
                   context_level, model_name, prompt_version, run_number,
                   timestamp
  Evaluation:      is_true_positive, explanation_correctness_score,
                   explanation_completeness_score, explanation_specificity_score,
                   quality_attribute_alignment, repair_correctness_score,
                   repair_actionability_score, hallucination_type,
                   success, parsing_failed, context_truncated
  Developer study: condition, understandability_score, correctness_score,
                   actionability_score, trust_score

Usage:
    python analyse_results.py --input experiments.jsonl --output output
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ── Constants ────────────────────────────────────────────────────────────────

FIG_SIZE = (8, 5)
DPI = 150

EXPLANATION_SCORES = [
    "explanation_correctness_score",
    "explanation_completeness_score",
    "explanation_specificity_score",
]
REPAIR_SCORES = [
    "repair_correctness_score",
    "repair_actionability_score",
]
DEVELOPER_SCORES = [
    "understandability_score",
    "correctness_score",
    "actionability_score",
    "trust_score",
]

CONTEXT_LEVEL_ORDER = ["minimal", "structural", "relational", "full"]


# ── Loading & cleaning ────────────────────────────────────────────────────────

def load(path: Path) -> pd.DataFrame:
    """Load an experiments file (JSONL, JSON, or CSV).

    Auto-detects JSONL vs JSON by content (number of non-blank lines), so a
    file mis-named ``experiments.json`` containing JSONL still loads fine.
    Reads as UTF-8-sig so a leading BOM is stripped transparently.
    """
    from io import StringIO
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(path, encoding="utf-8-sig")

    if suffix in (".jsonl", ".json"):
        with path.open("r", encoding="utf-8-sig") as fh:
            lines = [ln for ln in fh if ln.strip()]
        if not lines:
            return pd.DataFrame()

        # Heuristic: more than one non-blank line ⇒ JSONL, regardless of extension.
        # A single line could still be JSONL of length 1, so try JSONL first either way.
        try:
            return pd.read_json(StringIO("".join(lines)), lines=True)
        except ValueError:
            # Fall back to single-document JSON (e.g. an array of objects).
            return pd.read_json(StringIO("".join(lines)))

    raise ValueError(f"unsupported file type: {suffix} (expected .jsonl, .json or .csv)")


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise column names and coerce numeric score fields."""
    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    # Coerce all known score columns to numeric — invalid values become NaN.
    score_cols = EXPLANATION_SCORES + REPAIR_SCORES + DEVELOPER_SCORES + [
        "quality_attribute_alignment",
    ]
    for col in score_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Coerce booleans defensively (CSV stores them as strings).
    for col in ("is_true_positive", "success", "parsing_failed", "context_truncated"):
        if col in df.columns:
            df[col] = _to_bool(df[col])

    # Order context levels so plots come out in the natural Minimal→Full order.
    if "context_level" in df.columns:
        df["context_level"] = (
            df["context_level"].astype(str).str.strip().str.lower()
        )

    return df


def _to_bool(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    return s.astype(str).str.strip().str.lower().map(
        {"true": True, "1": True, "yes": True, "y": True,
         "false": False, "0": False, "no": False, "n": False}
    )


def has(df: pd.DataFrame, *cols: str) -> bool:
    """Return True iff every column is present. Used for guard clauses."""
    missing = [c for c in cols if c not in df.columns]
    if missing:
        warnings.warn(f"skipping analysis — missing columns: {missing}", stacklevel=2)
        return False
    return True


# ── Output helpers ────────────────────────────────────────────────────────────

def save_table(df: pd.DataFrame, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / f"{name}.csv", index=False)


def save_figure(fig: plt.Figure, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_dir / f"{name}.png", dpi=DPI, bbox_inches="tight")
    plt.close(fig)


def _bar(ax: plt.Axes, x_labels: list[str], values: np.ndarray, ylabel: str,
         title: str, rotate: bool = False) -> None:
    positions = np.arange(len(x_labels))
    ax.bar(positions, values)
    ax.set_xticks(positions)
    ax.set_xticklabels(x_labels, rotation=30 if rotate else 0, ha="right" if rotate else "center")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", linestyle="--", alpha=0.4)


def _grouped_bar(ax: plt.Axes, x_labels: list[str],
                 series: dict[str, np.ndarray],
                 ylabel: str, title: str) -> None:
    n_groups = len(x_labels)
    n_series = len(series)
    width = 0.8 / max(n_series, 1)
    positions = np.arange(n_groups)
    for i, (name, values) in enumerate(series.items()):
        offset = (i - (n_series - 1) / 2) * width
        ax.bar(positions + offset, values, width=width, label=name)
    ax.set_xticks(positions)
    ax.set_xticklabels(x_labels)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    ax.grid(axis="y", linestyle="--", alpha=0.4)


def _ordered_categories(values: pd.Series, preferred: list[str] | None = None) -> list[str]:
    """Return unique values, with `preferred` ordering applied where possible."""
    seen = list(values.dropna().unique())
    if preferred is None:
        return sorted(seen, key=str)
    head = [c for c in preferred if c in seen]
    tail = sorted([c for c in seen if c not in preferred], key=str)
    return head + tail


# ── 2. Experiment overview ────────────────────────────────────────────────────

def overview(df: pd.DataFrame, tables_dir: Path) -> None:
    rows = {"total_runs": [len(df)]}

    if "model_name" in df.columns:
        save_table(
            df.groupby("model_name").size().rename("runs").reset_index(),
            tables_dir, "runs_by_model",
        )

    if "anti_pattern_type" in df.columns:
        save_table(
            df.groupby("anti_pattern_type").size().rename("runs").reset_index(),
            tables_dir, "runs_by_anti_pattern",
        )

    if "context_level" in df.columns:
        save_table(
            df.groupby("context_level").size().rename("runs").reset_index(),
            tables_dir, "runs_by_context_level",
        )

    if "success" in df.columns:
        rows["failed_runs"] = [int((~df["success"].fillna(False)).sum())]
        rows["failure_rate"] = [float((~df["success"].fillna(False)).mean())]

    if "parsing_failed" in df.columns:
        rows["parsing_failures"] = [int(df["parsing_failed"].fillna(False).sum())]
        rows["parsing_failure_rate"] = [float(df["parsing_failed"].fillna(False).mean())]

    if "context_truncated" in df.columns:
        rows["context_truncations"] = [int(df["context_truncated"].fillna(False).sum())]

    save_table(pd.DataFrame(rows), tables_dir, "overview")


# ── 3. Context-level analysis ─────────────────────────────────────────────────

def context_analysis(df: pd.DataFrame, tables_dir: Path, figures_dir: Path) -> None:
    if not has(df, "context_level"):
        return

    # Aggregate every available metric in one pass.
    agg_cols = [c for c in EXPLANATION_SCORES + REPAIR_SCORES if c in df.columns]
    if not agg_cols and "hallucination_type" not in df.columns:
        warnings.warn("context analysis: no scores or hallucination column available — skipping")
        return

    table = df.groupby("context_level")[agg_cols].mean(numeric_only=True) if agg_cols else pd.DataFrame()

    if "hallucination_type" in df.columns:
        hall = (
            df.assign(_h=df["hallucination_type"].notna() & (df["hallucination_type"] != ""))
              .groupby("context_level")["_h"].mean()
              .rename("hallucination_rate")
        )
        table = table.join(hall, how="outer") if not table.empty else hall.to_frame()

    table = table.reindex(_ordered_categories(df["context_level"], CONTEXT_LEVEL_ORDER))
    save_table(table.reset_index(), tables_dir, "summary_by_context_level")

    levels = list(table.index)

    # Plot 1: explanation quality (each score as a series)
    expl_present = [c for c in EXPLANATION_SCORES if c in table.columns]
    if expl_present:
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _grouped_bar(
            ax, levels,
            {c.replace("_score", "").replace("explanation_", ""): table[c].to_numpy() for c in expl_present},
            ylabel="Mean score", title="Explanation quality by context level",
        )
        save_figure(fig, figures_dir, "context_explanation_quality")

    # Plot 2: hallucination rate
    if "hallucination_rate" in table.columns:
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _bar(ax, levels, table["hallucination_rate"].to_numpy(),
             ylabel="Hallucination rate", title="Hallucination rate by context level")
        save_figure(fig, figures_dir, "context_hallucination_rate")

    # Plot 3: repair actionability
    if "repair_actionability_score" in table.columns:
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _bar(ax, levels, table["repair_actionability_score"].to_numpy(),
             ylabel="Mean repair actionability",
             title="Repair actionability by context level")
        save_figure(fig, figures_dir, "context_repair_actionability")


# ── 4. Model comparison ──────────────────────────────────────────────────────

def model_analysis(df: pd.DataFrame, tables_dir: Path, figures_dir: Path) -> None:
    if not has(df, "model_name"):
        return

    agg_cols = [c for c in EXPLANATION_SCORES + REPAIR_SCORES if c in df.columns]
    table = df.groupby("model_name")[agg_cols].mean(numeric_only=True) if agg_cols else pd.DataFrame()

    if "hallucination_type" in df.columns:
        hall = (
            df.assign(_h=df["hallucination_type"].notna() & (df["hallucination_type"] != ""))
              .groupby("model_name")["_h"].mean().rename("hallucination_rate")
        )
        table = table.join(hall, how="outer") if not table.empty else hall.to_frame()

    if table.empty:
        warnings.warn("model analysis: no metrics available — skipping")
        return

    table = table.sort_index()
    save_table(table.reset_index(), tables_dir, "summary_by_model")

    models = list(table.index)

    expl_present = [c for c in EXPLANATION_SCORES if c in table.columns]
    if expl_present:
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _grouped_bar(
            ax, models,
            {c.replace("_score", "").replace("explanation_", ""): table[c].to_numpy() for c in expl_present},
            ylabel="Mean score", title="Explanation quality by model",
        )
        ax.tick_params(axis="x", labelrotation=20)
        save_figure(fig, figures_dir, "model_explanation_quality")

    if "hallucination_rate" in table.columns:
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _bar(ax, models, table["hallucination_rate"].to_numpy(),
             ylabel="Hallucination rate", title="Hallucination rate by model", rotate=True)
        save_figure(fig, figures_dir, "model_hallucination_rate")

    repair_present = [c for c in REPAIR_SCORES if c in table.columns]
    if repair_present:
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _grouped_bar(
            ax, models,
            {c.replace("_score", "").replace("repair_", ""): table[c].to_numpy() for c in repair_present},
            ylabel="Mean score", title="Repair quality by model",
        )
        ax.tick_params(axis="x", labelrotation=20)
        save_figure(fig, figures_dir, "model_repair_quality")


# ── 5. Anti-pattern comparison ───────────────────────────────────────────────

def anti_pattern_analysis(df: pd.DataFrame, tables_dir: Path, figures_dir: Path) -> None:
    if not has(df, "anti_pattern_type"):
        return

    agg_cols = [c for c in EXPLANATION_SCORES + REPAIR_SCORES if c in df.columns]
    table = df.groupby("anti_pattern_type")[agg_cols].mean(numeric_only=True) if agg_cols else pd.DataFrame()

    if "hallucination_type" in df.columns:
        hall = (
            df.assign(_h=df["hallucination_type"].notna() & (df["hallucination_type"] != ""))
              .groupby("anti_pattern_type")["_h"].mean().rename("hallucination_rate")
        )
        table = table.join(hall, how="outer") if not table.empty else hall.to_frame()

    if table.empty:
        warnings.warn("anti-pattern analysis: no metrics available — skipping")
        return

    table = table.sort_index()
    save_table(table.reset_index(), tables_dir, "summary_by_anti_pattern")

    types = list(table.index)

    expl_present = [c for c in EXPLANATION_SCORES if c in table.columns]
    if expl_present:
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _grouped_bar(
            ax, types,
            {c.replace("_score", "").replace("explanation_", ""): table[c].to_numpy() for c in expl_present},
            ylabel="Mean score", title="Explanation quality by anti-pattern",
        )
        ax.tick_params(axis="x", labelrotation=20)
        save_figure(fig, figures_dir, "anti_pattern_explanation_quality")

    if "hallucination_rate" in table.columns:
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _bar(ax, types, table["hallucination_rate"].to_numpy(),
             ylabel="Hallucination rate", title="Hallucination rate by anti-pattern", rotate=True)
        save_figure(fig, figures_dir, "anti_pattern_hallucination_rate")


# ── 6. Developer-study analysis ──────────────────────────────────────────────

def developer_analysis(df: pd.DataFrame, tables_dir: Path, figures_dir: Path) -> None:
    metrics = [c for c in DEVELOPER_SCORES if c in df.columns]
    if not metrics or "condition" not in df.columns:
        warnings.warn("developer-study analysis: skipped (no condition or metric columns present)")
        return

    table = df.groupby("condition")[metrics].mean(numeric_only=True).round(3)
    save_table(table.reset_index(), tables_dir, "summary_by_developer_condition")

    conditions = list(table.index)
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    _grouped_bar(
        ax, conditions,
        {m.replace("_score", ""): table[m].to_numpy() for m in metrics},
        ylabel="Mean score", title="Developer study — condition comparison",
    )
    save_figure(fig, figures_dir, "developer_condition_comparison")

    # Wilcoxon signed-rank test if data is paired (same instance_id seen in both conditions).
    if "instance_id" in df.columns and df["condition"].nunique() == 2:
        try:
            from scipy.stats import wilcoxon
        except ImportError:
            warnings.warn("scipy not installed — skipping Wilcoxon test")
            return

        cond_a, cond_b = sorted(df["condition"].dropna().unique())
        rows = []
        for metric in metrics:
            paired = (
                df[["instance_id", "condition", metric]]
                .dropna()
                .pivot_table(index="instance_id", columns="condition",
                             values=metric, aggfunc="mean")
                .dropna()
            )
            if paired.shape[0] < 2 or paired.shape[1] < 2:
                rows.append({"metric": metric, "n_pairs": paired.shape[0],
                             "median_diff": np.nan, "statistic": np.nan, "p_value": np.nan})
                continue

            diff = paired[cond_b] - paired[cond_a]
            try:
                stat, p = wilcoxon(diff, zero_method="wilcox", correction=False)
            except ValueError:
                stat, p = (np.nan, np.nan)

            rows.append({
                "metric": metric,
                "n_pairs": paired.shape[0],
                f"median_{cond_a}": paired[cond_a].median(),
                f"median_{cond_b}": paired[cond_b].median(),
                "median_diff": diff.median(),
                "statistic": stat,
                "p_value": p,
            })

        save_table(pd.DataFrame(rows), tables_dir, "developer_wilcoxon")


# ── ISO/IEC 25010 quality-attribute alignment ────────────────────────────────

def _ensure_list(value) -> list:
    """Coerce a cell to a Python list — tolerates JSON-array strings (CSV) and lists (JSONL)."""
    if isinstance(value, list):
        return value
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        s = value.strip()
        if s.startswith("["):
            try:
                import json as _json
                parsed = _json.loads(s)
                return parsed if isinstance(parsed, list) else []
            except _json.JSONDecodeError:
                return []
    return []


def quality_alignment_analysis(df: pd.DataFrame, tables_dir: Path, figures_dir: Path) -> None:
    """Alignment of LLM-mentioned vs. literature-expected ISO/IEC 25010 attributes.

    Two complementary metrics:
      * alignment_rate    = mean(quality_attribute_alignment) per group     (binary, lower-bound)
      * attribute_coverage = mean(|expected ∩ mentioned| / |expected|)      (continuous, finer)
    """
    if "quality_attribute_alignment" not in df.columns:
        warnings.warn("quality alignment: skipped (no quality_attribute_alignment column)")
        return

    work = df.copy()
    work["quality_attribute_alignment"] = pd.to_numeric(
        work["quality_attribute_alignment"], errors="coerce"
    )

    # Per-row coverage = |expected ∩ mentioned| / |expected|, NaN where expected is empty.
    if "expected_quality_attributes" in work.columns and \
       "llm_quality_attributes_mentioned" in work.columns:
        def _row_coverage(row) -> float:
            expected  = set(_ensure_list(row.get("expected_quality_attributes")))
            mentioned = set(_ensure_list(row.get("llm_quality_attributes_mentioned")))
            return len(expected & mentioned) / len(expected) if expected else np.nan

        work["_coverage"] = work.apply(_row_coverage, axis=1)
    else:
        work["_coverage"] = np.nan

    for group_col, file_tag, title_tag, rotate in [
        ("model_name",        "by_model",         "model",        True),
        ("context_level",     "by_context_level", "context level", False),
        ("anti_pattern_type", "by_anti_pattern",  "anti-pattern",  True),
    ]:
        if group_col not in work.columns:
            continue

        agg = work.groupby(group_col).agg(
            n=("quality_attribute_alignment", "count"),
            alignment_rate=("quality_attribute_alignment", "mean"),
            attribute_coverage=("_coverage", "mean"),
        ).round(3)

        # Re-order context levels for readability.
        if group_col == "context_level":
            agg = agg.reindex(_ordered_categories(work[group_col], CONTEXT_LEVEL_ORDER))

        save_table(agg.reset_index(), tables_dir, f"alignment_{file_tag}")

        # Figure: alignment rate
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _bar(ax, list(agg.index.astype(str)), agg["alignment_rate"].to_numpy(),
             ylabel="Alignment rate (proportion of runs with ≥1 expected attribute mentioned)",
             title=f"Quality-attribute alignment by {title_tag}", rotate=rotate)
        ax.set_ylim(0, 1)
        save_figure(fig, figures_dir, f"quality_alignment_{file_tag}")

        # Figure: attribute coverage (only when meaningful — at least one non-NaN)
        if agg["attribute_coverage"].notna().any():
            fig, ax = plt.subplots(figsize=FIG_SIZE)
            _bar(ax, list(agg.index.astype(str)), agg["attribute_coverage"].to_numpy(),
                 ylabel="Mean attribute coverage |expected ∩ mentioned| / |expected|",
                 title=f"Attribute coverage by {title_tag}", rotate=rotate)
            ax.set_ylim(0, 1)
            save_figure(fig, figures_dir, f"attribute_coverage_{file_tag}")


# ── 7. Hallucination analysis ────────────────────────────────────────────────

def hallucination_analysis(df: pd.DataFrame, tables_dir: Path, figures_dir: Path) -> None:
    if "hallucination_type" not in df.columns:
        warnings.warn("hallucination analysis: skipped (no hallucination_type column)")
        return

    df = df.copy()
    df["_hallucinated"] = df["hallucination_type"].notna() & (df["hallucination_type"] != "")

    overall = pd.DataFrame({"total_hallucination_rate": [df["_hallucinated"].mean()]})
    save_table(overall, tables_dir, "hallucination_overall")

    # Type distribution
    type_counts = (
        df.loc[df["_hallucinated"], "hallucination_type"]
          .value_counts()
          .rename("count")
          .reset_index()
          .rename(columns={"index": "hallucination_type"})
    )
    save_table(type_counts, tables_dir, "hallucination_type_distribution")

    if not type_counts.empty:
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _bar(ax, type_counts["hallucination_type"].astype(str).tolist(),
             type_counts["count"].to_numpy(),
             ylabel="Count", title="Hallucination type distribution", rotate=True)
        save_figure(fig, figures_dir, "hallucination_type_distribution")

    if "model_name" in df.columns:
        per_model = df.groupby("model_name")["_hallucinated"].mean().rename("hallucination_rate")
        save_table(per_model.reset_index(), tables_dir, "hallucination_by_model")
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _bar(ax, list(per_model.index), per_model.to_numpy(),
             ylabel="Hallucination rate", title="Hallucination rate by model", rotate=True)
        save_figure(fig, figures_dir, "hallucination_rate_by_model")

    if "context_level" in df.columns:
        per_ctx = (
            df.groupby("context_level")["_hallucinated"].mean()
              .reindex(_ordered_categories(df["context_level"], CONTEXT_LEVEL_ORDER))
              .rename("hallucination_rate")
        )
        save_table(per_ctx.reset_index(), tables_dir, "hallucination_by_context_level")
        fig, ax = plt.subplots(figsize=FIG_SIZE)
        _bar(ax, list(per_ctx.index), per_ctx.to_numpy(),
             ylabel="Hallucination rate", title="Hallucination rate by context level")
        save_figure(fig, figures_dir, "hallucination_rate_by_context_level")


# ── Driver ───────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyse a HybridLens experiments file (JSONL/CSV) and emit "
                    "thesis-ready tables and figures.")
    parser.add_argument("--input", "-i", required=True, type=Path,
                        help="Path to experiments.jsonl or experiments.csv")
    parser.add_argument("--output", "-o", default=Path("output"), type=Path,
                        help="Output root directory (default: ./output)")
    parser.add_argument("--only-true-positives", action="store_true",
                        help="Restrict score-based analyses to rows where "
                             "is_true_positive == True (failures still reported separately).")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 2

    figures_dir = args.output / "figures"
    tables_dir  = args.output / "tables"

    # Show all warnings inline so missing-column messages are visible during a run.
    warnings.simplefilter("always")

    df_raw = load(args.input)
    df     = clean(df_raw)

    print(f"loaded {len(df)} rows, {len(df.columns)} columns from {args.input}")

    # 2. Overview always uses the full dataset (failures included).
    overview(df, tables_dir)

    # Optional filter for quality-score analyses — failed runs and false positives
    # don't have meaningful scores. The overview still reflects them.
    df_scored = df.copy()
    if args.only_true_positives and "is_true_positive" in df.columns:
        df_scored = df_scored[df_scored["is_true_positive"].fillna(False)]
        print(f"  filtering to true positives: {len(df_scored)} rows kept")
    if "success" in df.columns:
        df_scored = df_scored[df_scored["success"].fillna(True)]

    # 3 – 5. Quality + hallucination breakdowns
    context_analysis(df_scored,      tables_dir, figures_dir)
    model_analysis(df_scored,        tables_dir, figures_dir)
    anti_pattern_analysis(df_scored, tables_dir, figures_dir)

    # 6. Developer study (uses the original df — these scores aren't tied to success)
    developer_analysis(df, tables_dir, figures_dir)

    # ISO/IEC 25010 alignment — uses the scored subset so failed/parse-error rows
    # (which have alignment == null) don't dilute the proportions.
    quality_alignment_analysis(df_scored, tables_dir, figures_dir)

    # 7. Hallucinations are computed on the unfiltered df so we don't hide them.
    hallucination_analysis(df, tables_dir, figures_dir)

    print(f"\ndone — tables in {tables_dir.resolve()}")
    print(f"       figures in {figures_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
