"""Automated evaluation for HybridLens run traces.

Consumes raw generation, agentic, and verified-repair JSONL records directly.
Every reported outcome is derived mechanically from persisted pipeline fields:
parse/failure status, lexical quality-attribute alignment, agentic instance
matching, build/re-measure verification, and whole-solution analyzer deltas.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from pathlib import Path

import pandas as pd

FRONTIER_MODEL = "gpt-5.4"
CONTEXT_ORDER = ["minimal", "structural", "relational", "full"]
LADDER_ORDER = ["unapplicable", "build_fails", "builds_unresolved", "resolved"]


def expand_inputs(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = [Path(path) for path in glob.glob(pattern)]
        if matches:
            paths.extend(matches)
        elif Path(pattern).exists():
            paths.append(Path(pattern))
    return sorted(set(paths))


def load_records(patterns: list[str]) -> pd.DataFrame:
    records: list[dict] = []
    for path in expand_inputs(patterns):
        try:
            if path.suffix.lower() == ".json":
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                records.extend(payload if isinstance(payload, list) else [payload])
                continue
            with path.open("r", encoding="utf-8-sig") as handle:
                for line_number, raw in enumerate(handle, start=1):
                    if not raw.strip():
                        continue
                    try:
                        records.append(json.loads(raw))
                    except json.JSONDecodeError as exc:
                        print(f"warning: {path}:{line_number}: {exc}", file=sys.stderr)
        except OSError as exc:
            print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
    return clean(pd.DataFrame(records))


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes"}


def _bool_or_na(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return float("nan")
    return _bool(value)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df.columns = [str(column).strip().lower().replace(" ", "_") for column in df.columns]
    for column in ("context_level", "architecture", "model_name", "anti_pattern_type",
                   "verified_repair_ladder", "agentic_snapshot"):
        if column in df.columns:
            df[column] = df[column].astype("string").str.strip().str.lower()
    if "architecture" not in df.columns:
        df["architecture"] = "hybrid"
    if "context_level" in df.columns and "model_name" in df.columns:
        baseline = ((df["context_level"] == "analyser_only") |
                    (df["model_name"] == "static-analyser"))
        df.loc[baseline, "architecture"] = "analyser_only"
    if {"file_path", "symbol_name", "line"}.issubset(df.columns):
        df["instance_key"] = (df["file_path"].astype(str) + "::" +
                              df["symbol_name"].astype(str) + "::" +
                              df["line"].astype(str))
    if "is_spurious" in df.columns:
        df["is_spurious"] = df["is_spurious"].map(_bool_or_na)
    for column in ("verified_repair_success", "context_truncated"):
        if column in df.columns:
            df[column] = df[column].map(_bool)
    for column in ("quality_attribute_alignment", "input_tokens", "output_tokens", "duration_ms"):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def save_table(df: pd.DataFrame, directory: Path, name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    df.to_csv(directory / f"{name}.csv", index=False)


def wilson(successes: int, n: int) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    z = 1.959963984540054
    proportion = successes / n
    denominator = 1 + z * z / n
    centre = (proportion + z * z / (2 * n)) / denominator
    half = z * math.sqrt(proportion * (1 - proportion) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def generation_rows(df: pd.DataFrame) -> pd.DataFrame:
    if "verified_repair_ladder" not in df.columns:
        return df
    return df[df["verified_repair_ladder"].isna()]


def verified_rows(df: pd.DataFrame, *, final_only: bool = False) -> pd.DataFrame:
    if "verified_repair_ladder" not in df.columns:
        return df.iloc[0:0]
    result = df[df["verified_repair_ladder"].notna()].copy()
    if final_only and "agentic_snapshot" in result.columns:
        result = result[result["agentic_snapshot"].isna() | (result["agentic_snapshot"] == "final")]
    return result


def record_summaries(df: pd.DataFrame, tables: Path) -> None:
    generated = generation_rows(df)
    verified = verified_rows(df)
    errors = generated.get("error_status", pd.Series(index=generated.index, dtype=object))
    save_table(pd.DataFrame([{
        "records": len(df),
        "generation_records": len(generated),
        "verification_records": len(verified),
        "generation_failures": int(errors.notna().sum()),
        "distinct_instances": generated.get("instance_key", pd.Series(dtype=str)).nunique(),
    }]), tables, "run_overview")
    dimensions = [column for column in ("architecture", "context_level", "anti_pattern_type")
                  if column in generated]
    if dimensions:
        save_table(generated.groupby(dimensions, dropna=False).size().rename("n").reset_index(),
                   tables, "generation_counts")
    if "error_status" in generated:
        failed = generated[generated["error_status"].notna()]
        if not failed.empty:
            by = [column for column in ("architecture", "context_level", "error_status") if column in failed]
            save_table(failed.groupby(by, dropna=False).size().rename("n").reset_index(),
                       tables, "generation_failures")


def quality_attribute_alignment(df: pd.DataFrame, tables: Path) -> None:
    generated = generation_rows(df)
    if "quality_attribute_alignment" not in generated:
        return
    usable = generated[generated["quality_attribute_alignment"].notna()].copy()
    if usable.empty:
        return
    usable["aligned"] = usable["quality_attribute_alignment"] > 0
    rows: list[dict] = []
    for dimension in ("architecture", "context_level", "anti_pattern_type"):
        if dimension not in usable:
            continue
        for value, group in usable.groupby(dimension, dropna=False):
            n = len(group)
            aligned = int(group["aligned"].sum())
            lo, hi = wilson(aligned, n)
            rows.append({"dimension": dimension, "value": value, "n": n,
                         "aligned": aligned, "alignment_rate": aligned / n,
                         "ci_lo": lo, "ci_hi": hi})
    save_table(pd.DataFrame(rows), tables, "quality_attribute_alignment")


def agentic_detection(df: pd.DataFrame, tables: Path) -> None:
    generated = generation_rows(df)
    if "architecture" not in generated or "instance_key" not in generated:
        return
    known = generated[generated["architecture"] != "agentic"][["anti_pattern_type", "instance_key"]].drop_duplicates()
    agentic = generated[generated["architecture"] == "agentic"]
    if "is_spurious" not in agentic:
        return
    findings = agentic[agentic["is_spurious"].notna()]
    if findings.empty:
        return
    matched = set(findings.loc[findings["is_spurious"] == False, "matched_instance_id"].dropna()) \
        if "matched_instance_id" in findings else set()
    rows: list[dict] = []
    for anti_pattern, group in known.groupby("anti_pattern_type"):
        keys = set(group["instance_key"])
        recovered = len(keys & matched)
        lo, hi = wilson(recovered, len(keys))
        rows.append({"anti_pattern_type": anti_pattern, "known": len(keys), "recovered": recovered,
                     "recall": recovered / len(keys) if keys else float("nan"),
                     "ci_lo": lo, "ci_hi": hi})
    all_keys = set(known["instance_key"])
    recovered = len(all_keys & matched)
    lo, hi = wilson(recovered, len(all_keys))
    rows.append({"anti_pattern_type": "ALL", "known": len(all_keys), "recovered": recovered,
                 "recall": recovered / len(all_keys) if all_keys else float("nan"),
                 "ci_lo": lo, "ci_hi": hi})
    save_table(pd.DataFrame(rows), tables, "agentic_recall")
    spurious = int((findings["is_spurious"] == True).sum())
    save_table(pd.DataFrame([{"agentic_findings": len(findings),
                              "matched": int((findings["is_spurious"] == False).sum()),
                              "spurious": spurious,
                              "spurious_rate": spurious / len(findings)}]),
               tables, "agentic_spurious_summary")


def _ladder_counts(group: pd.DataFrame) -> dict:
    return {name: int((group["verified_repair_ladder"] == name).sum()) for name in LADDER_ORDER}


def _repair_summary(group: pd.DataFrame, prefix: dict) -> dict:
    n = len(group)
    resolved = int(group.get("verified_repair_success", pd.Series(dtype=bool)).sum()) if n else 0
    lo, hi = wilson(resolved, n)
    return {**prefix, "n": n, "resolved": resolved,
            "success_pct": 100 * resolved / n if n else float("nan"),
            "ci_lo_pct": 100 * lo, "ci_hi_pct": 100 * hi,
            **_ladder_counts(group)}


def _minimal_frontier(df: pd.DataFrame) -> pd.DataFrame:
    result = df
    if "model_name" in result and (result["model_name"] == FRONTIER_MODEL).any():
        result = result[result["model_name"] == FRONTIER_MODEL]
    if "context_level" in result and (result["context_level"] == "minimal").any():
        result = result[result["context_level"] == "minimal"]
    return result


def _success_by_instance(df: pd.DataFrame, architecture: str, snapshot: str | None = None) -> pd.Series:
    group = df[df["architecture"] == architecture]
    if snapshot is not None and "agentic_snapshot" in group:
        group = group[group["agentic_snapshot"] == snapshot]
    if group.empty or "instance_key" not in group:
        return pd.Series(dtype=bool)
    return group.groupby("instance_key")["verified_repair_success"].max().astype(bool)


def _mcnemar(a_only: int, b_only: int) -> float:
    discordant = a_only + b_only
    if discordant == 0:
        return float("nan")
    if discordant < 25:
        lower = min(a_only, b_only)
        one_tail = sum(math.comb(discordant, value) for value in range(lower + 1)) / (2 ** discordant)
        return min(1.0, 2 * one_tail)
    statistic = (abs(a_only - b_only) - 1) ** 2 / discordant
    return math.erfc(math.sqrt(statistic / 2))


def _paired(a: pd.Series, b: pd.Series, label: str, isolates: str) -> dict:
    pairs = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna().astype(bool)
    a_only = int((pairs.a & ~pairs.b).sum())
    b_only = int((~pairs.a & pairs.b).sum())
    difference = float(pairs.a.mean() - pairs.b.mean()) if len(pairs) else float("nan")
    return {"contrast": label, "isolates": isolates, "n_pairs": len(pairs),
            "a_yes_b_no": a_only, "a_no_b_yes": b_only,
            "risk_diff": difference, "mcnemar_p": _mcnemar(a_only, b_only)}


def verified_repair(df: pd.DataFrame, tables: Path) -> None:
    all_verified = verified_rows(df)
    if all_verified.empty:
        return
    final = verified_rows(df, final_only=True)
    base = _minimal_frontier(final)
    by_architecture = [_repair_summary(group, {"architecture": architecture})
                       for architecture, group in base.groupby("architecture")]
    save_table(pd.DataFrame(by_architecture), tables, "verified_repair_by_architecture")

    hybrid = all_verified[all_verified["architecture"] == "hybrid"]
    if "model_name" in hybrid and (hybrid["model_name"] == FRONTIER_MODEL).any():
        hybrid = hybrid[hybrid["model_name"] == FRONTIER_MODEL]
    context_rows: list[dict] = []
    for index, context in enumerate(CONTEXT_ORDER):
        group = hybrid[hybrid["context_level"] == context]
        if not group.empty:
            context_rows.append(_repair_summary(group, {"context_level": context,
                                                         "context_ord": index}))
    if context_rows:
        save_table(pd.DataFrame(context_rows), tables, "verified_repair_by_context")
        long_rows = [{"instance_key": row.get("instance_key"),
                      "context_level": row.get("context_level"),
                      "context_ord": CONTEXT_ORDER.index(row.get("context_level")),
                      "verified_repair_success": int(bool(row.get("verified_repair_success")))}
                     for _, row in hybrid.iterrows() if row.get("context_level") in CONTEXT_ORDER]
        save_table(pd.DataFrame(long_rows), tables, "verified_repair_context_long")

    hybrid_success = _success_by_instance(base, "hybrid")
    agentic_success = _success_by_instance(base, "agentic")
    if len(hybrid_success) and len(agentic_success):
        comparison = _paired(hybrid_success, agentic_success,
                             "hybrid_vs_agentic_final", "architecture")
        save_table(pd.DataFrame([comparison]), tables,
                   "verified_repair_mcnemar_hybrid_vs_agentic")

    if "agentic_snapshot" not in all_verified:
        return
    square = _minimal_frontier(all_verified)
    cells: list[dict] = []
    for arm, architecture in (("grounded", "grounded_iterative"), ("ungrounded", "agentic")):
        for snapshot in ("first_build", "final"):
            group = square[(square["architecture"] == architecture) &
                           (square["agentic_snapshot"] == snapshot)]
            if not group.empty:
                cells.append(_repair_summary(group, {"arm": arm, "architecture": architecture,
                                                      "snapshot": snapshot,
                                                      "control_structure": "single_pass" if snapshot == "first_build" else "iterative"}))
    hybrid_group = square[square["architecture"] == "hybrid"]
    if not hybrid_group.empty:
        cells.append(_repair_summary(hybrid_group, {"arm": "comparator", "architecture": "hybrid",
                                                    "snapshot": "applied_literally",
                                                    "control_structure": "single_pass"}))
    if cells:
        save_table(pd.DataFrame(cells), tables, "verified_repair_2x2")

    grounded_first = _success_by_instance(square, "grounded_iterative", "first_build")
    grounded_final = _success_by_instance(square, "grounded_iterative", "final")
    agentic_first = _success_by_instance(square, "agentic", "first_build")
    agentic_final = _success_by_instance(square, "agentic", "final")
    contrasts: list[dict] = []
    if len(grounded_final) and len(agentic_final):
        contrasts.append(_paired(grounded_final, agentic_final,
                                 "grounded_vs_ungrounded_iterative", "grounding @ iterative"))
    if len(grounded_first) and len(agentic_first):
        contrasts.append(_paired(grounded_first, agentic_first,
                                 "grounded_vs_ungrounded_single_pass", "grounding @ single-pass"))
    if len(grounded_final) and len(grounded_first):
        contrasts.append(_paired(grounded_final, grounded_first,
                                 "grounded_final_vs_first_build", "iteration @ grounded"))
    if len(agentic_final) and len(agentic_first):
        contrasts.append(_paired(agentic_final, agentic_first,
                                 "ungrounded_final_vs_first_build", "iteration @ ungrounded"))
    if contrasts:
        save_table(pd.DataFrame(contrasts), tables, "verified_repair_2x2_contrasts")


def _number(value, default=0):
    if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
        return value
    return default


def quality_impact(df: pd.DataFrame, tables: Path) -> None:
    if "quality_delta" not in df:
        return
    rows = verified_rows(df, final_only=True)
    rows = rows[rows["quality_delta"].apply(lambda value: isinstance(value, dict))].copy()
    if rows.empty:
        return
    rows["smell_delta"] = rows["quality_delta"].apply(lambda value: _number(value.get("smell_total_delta")))
    rows["collateral"] = rows["quality_delta"].apply(lambda value: _bool(value.get("smell_collateral")))
    rows["ca_available"] = rows["quality_delta"].apply(lambda value: _bool(value.get("ca_available")))
    rows["ca_headline_delta"] = rows["quality_delta"].apply(lambda value: _number(value.get("ca_headline_total_delta")))
    summaries: list[dict] = []
    for architecture, group in _minimal_frontier(rows).groupby("architecture"):
        ca = group[group["ca_available"]]
        summaries.append({"architecture": architecture, "n_built": len(group),
                          "smell_delta_mean": group["smell_delta"].mean(),
                          "collateral_n": int(group["collateral"].sum()),
                          "n_ca_available": len(ca),
                          "ca_headline_delta_mean": ca["ca_headline_delta"].mean() if len(ca) else float("nan"),
                          "ca_headline_worse_n": int((ca["ca_headline_delta"] > 0).sum()),
                          "ca_headline_better_n": int((ca["ca_headline_delta"] < 0).sum())})
    save_table(pd.DataFrame(summaries), tables, "quality_impact_by_architecture")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate automated quality-evaluation reports from raw run traces.")
    parser.add_argument("--input", "-i", required=True, nargs="+",
                        help="Raw JSON/JSONL paths or glob patterns.")
    parser.add_argument("--verified", nargs="*", default=[],
                        help="Optional additional verified-repair paths or glob patterns.")
    parser.add_argument("--output", "-o", type=Path, default=Path("output"))
    args = parser.parse_args(argv)

    df = load_records([*args.input, *args.verified])
    if df.empty:
        print("error: no run records found", file=sys.stderr)
        return 2
    if "run_id" in df:
        df = df.drop_duplicates(subset=["run_id"], keep="last")
    tables = args.output / "tables"
    record_summaries(df, tables)
    quality_attribute_alignment(df, tables)
    agentic_detection(df, tables)
    verified_repair(df, tables)
    quality_impact(df, tables)
    print(f"loaded {len(df)} unique record(s)")
    print(f"automated reports: {tables.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
