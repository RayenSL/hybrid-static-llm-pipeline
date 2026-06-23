"""
HybridLens run-trace loader and analysis primitives.

Each line in a `runs/*.jsonl` file is one RunRecord written by the C# pipeline
(see HybridLens.Core.Models.RunRecord). This module loads one or many such
files into a tidy pandas DataFrame and exposes the queries the thesis needs:

    - failure_rates       : honest reporting of API/parse/empty/cancel errors  (Req #8)
    - output_uniqueness   : does context level actually change the answer?     (RQ — context effect)
    - run_variance        : run-to-run stability of the same condition          (Req #5)
    - token_cost          : input/output token + duration aggregates per cell
    - parse_failures      : rows where structured-output parsing failed

Design notes:
    * No plotting here — the module returns DataFrames; users plot in notebooks.
    * Every function is pure: pass a DataFrame in, get a DataFrame out.
    * `load(*paths)` accepts globs and tags each row with its source `campaign`
      (= filename stem) so cross-campaign comparisons are one groupby away.
"""
from __future__ import annotations

import glob as _glob
import hashlib
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import pandas as pd


# ── Loading ───────────────────────────────────────────────────────────────────

def load(*patterns: str) -> pd.DataFrame:
    """Load one or many `runs/*.jsonl` files into a single DataFrame.

    Each pattern may be a literal path or a glob (`runs/*.jsonl`).  The source
    filename stem is added as a `campaign` column so multiple campaigns can be
    concatenated and compared.

    >>> df = load("runs/*.jsonl")
    >>> df.campaign.unique()
    array(['20260504-pilot', '20260507-final'], dtype=object)
    """
    paths = _expand(patterns)
    if not paths:
        raise FileNotFoundError(f"no files matched: {patterns}")

    frames = []
    for p in paths:
        # utf-8-sig strips a leading BOM transparently; pandas' ujson backend
        # rejects BOMs, so files written by older C# runs (pre-no-BOM fix)
        # would otherwise fail with "Expected object or value".
        with open(p, "r", encoding="utf-8-sig") as fh:
            lines = [ln for ln in fh if ln.strip()]
        if not lines:
            continue
        from io import StringIO
        frame = pd.read_json(StringIO("".join(lines)), lines=True)
        frame["campaign"] = Path(p).stem
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)

    # Normalise types — JSONL preserves them but be defensive.
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return df


def _expand(patterns: Iterable[str]) -> list[str]:
    out: list[str] = []
    for pat in patterns:
        matches = _glob.glob(pat)
        out.extend(matches if matches else ([pat] if Path(pat).exists() else []))
    return sorted(set(out))


# ── High-level summary ────────────────────────────────────────────────────────

def summary(df: pd.DataFrame) -> pd.Series:
    """One-shot overview of the loaded trace."""
    return pd.Series({
        "rows":              len(df),
        "campaigns":         df["campaign"].nunique() if "campaign" in df else 1,
        "findings":          df.groupby(["file_path", "symbol_name", "line"]).ngroups,
        "models":            df["model_name"].nunique(),
        "context_levels":    df["context_level"].nunique(),
        "prompt_versions":   df["prompt_version"].nunique(),
        "max_run_number":    int(df["run_number"].max()),
        "errors":            int(df["error_status"].notna().sum()),
        "parse_failures":    int((df["parse_status"] == "failed").sum()),
        "earliest":          df["timestamp"].min(),
        "latest":            df["timestamp"].max(),
    })


# ── Req #8: honest failure reporting ──────────────────────────────────────────

def failure_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Failure rate (% of rows with non-null error_status) per (model × context_level)."""
    grouped = df.groupby(["model_name", "context_level"])
    rate = grouped["error_status"].apply(lambda s: s.notna().mean())
    counts = grouped["error_status"].apply(lambda s: s.notna().sum())
    total = grouped.size().rename("total")
    return pd.concat([
        counts.rename("errors"),
        total,
        (rate * 100).round(2).rename("error_pct"),
    ], axis=1).reset_index()


def error_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Counts of each error_status category — `api_failure`, `parse_failure`, etc."""
    return (
        df[df["error_status"].notna()]
        .groupby(["model_name", "context_level", "error_status"])
        .size()
        .rename("count")
        .reset_index()
        .sort_values(["model_name", "context_level", "count"], ascending=[True, True, False])
    )


# ── RQ: does context level matter? ────────────────────────────────────────────

def output_uniqueness(df: pd.DataFrame, *, field: str = "parsed_explanation") -> pd.DataFrame:
    """For each (finding × model), how many distinct outputs were produced across context levels?

    `unique_outputs == 1` means the model effectively ignored context.
    `unique_outputs == n_levels` means context fully drove the answer.
    """
    df = df.copy()
    df["_hash"] = df[field].fillna("").apply(_short_hash)
    grouped = df.groupby(["file_path", "symbol_name", "line", "model_name"])
    return (
        grouped.agg(
            unique_outputs=("_hash", "nunique"),
            levels_seen=("context_level", "nunique"),
        )
        .reset_index()
    )


# ── Req #5: run-to-run variance ───────────────────────────────────────────────

def run_variance(df: pd.DataFrame, *, field: str = "parsed_explanation") -> pd.DataFrame:
    """Pairwise text similarity across `run_number` within each fixed condition.

    Returns mean SequenceMatcher ratio in [0, 1] per
    (finding × model × context_level). 1.0 = perfectly stable; lower = noisier.
    """
    keys = ["file_path", "symbol_name", "line", "model_name", "context_level"]

    def _stability(group: pd.DataFrame) -> float | None:
        texts = group[field].dropna().astype(str).tolist()
        if len(texts) < 2:
            return None
        sims = [
            SequenceMatcher(None, a, b).ratio()
            for i, a in enumerate(texts) for b in texts[i + 1:]
        ]
        return sum(sims) / len(sims)

    return (
        df.groupby(keys)
          .apply(_stability, include_groups=False)
          .rename("mean_similarity")
          .reset_index()
    )


# ── Cost & latency ────────────────────────────────────────────────────────────

def token_cost(df: pd.DataFrame) -> pd.DataFrame:
    """Mean and total token usage + latency per (model × context_level)."""
    return (
        df.groupby(["model_name", "context_level"])
          .agg(
              n=("run_id", "count"),
              input_tokens_mean=("input_tokens", "mean"),
              input_tokens_sum=("input_tokens", "sum"),
              output_tokens_mean=("output_tokens", "mean"),
              output_tokens_sum=("output_tokens", "sum"),
              duration_ms_mean=("duration_ms", "mean"),
              duration_ms_p95=("duration_ms", lambda s: s.quantile(0.95)),
          )
          .round(2)
          .reset_index()
    )


# ── Parse failures (qualitative inspection) ───────────────────────────────────

def parse_failures(df: pd.DataFrame, *, limit: int = 50) -> pd.DataFrame:
    """Rows where structured-response parsing failed — read raw_llm_output by hand for the thesis."""
    cols = ["model_name", "context_level", "run_number",
            "anti_pattern_type", "symbol_name", "raw_llm_output", "error_message"]
    return (
        df[df["parse_status"] == "failed"][cols]
        .head(limit)
        .reset_index(drop=True)
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _short_hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]
