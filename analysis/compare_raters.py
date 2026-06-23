"""
Inter-rater reliability (IRR) for the rubric in Appendix B of the thesis.

Computes per-dimension agreement between two raters (R1 and R2) on the IRR
subset, then reports:

  * Cohen's weighted κ (linear weights) for each ordinal explanation/repair
    dimension, with Landis–Koch interpretation (§B.8.2).
  * Cohen's κ (binary) per hallucination category, plus mean Jaccard agreement
    across the multi-label hallucination set.
  * The acceptance verdict against the κ ≥ 0.60 threshold (§B.8.2).
  * A list of persistent disagreements per dimension for §B.9 review.

Usage:
    python compare_raters.py --r1 experiments.jsonl --r2 experiments_R2.jsonl
    python compare_raters.py --r1 experiments.jsonl --r2 experiments_R2.jsonl \\
                             --output output/irr/ --json-out
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── Constants — match the scoring schema exactly ─────────────────────────────

ORDINAL_VALUES = ("poor", "adequate", "good")
ORDINAL_MAP = {v: i for i, v in enumerate(ORDINAL_VALUES)}

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
ORDINAL_DIMS = EXPLANATION_DIMS + REPAIR_DIMS

HALLUCINATION_CATEGORIES = [
    "factual_fabrication",
    "context_inconsistency",
    "intent_mismatch",
    "incomplete_suggestion",
    "irrelevant_suggestion",
    "risky_repair",
    "over_generalisation",
]

LANDIS_KOCH = [
    (0.80, "strong agreement — rubric is reliable"),
    (0.60, "substantial agreement — acceptable"),
    (0.40, "moderate agreement — rubric requires refinement"),
    (-1.0, "poor agreement — dimension is not reliably measurable"),
]


# ── I/O ──────────────────────────────────────────────────────────────────────

def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                rows.append(json.loads(raw))
            except json.JSONDecodeError as ex:
                print(f"  [warn] skipped malformed row: {ex}", file=sys.stderr)
    return rows


def index_by_run_id(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rows:
        rid = r.get("run_id")
        if rid is None:
            continue
        out[rid] = r  # last write wins (resume case)
    return out


# ── Cohen's κ (manual implementation — no scipy needed) ──────────────────────

def cohens_kappa(pairs: list[tuple[int, int]], k: int, *, weighted: bool = False) -> float | None:
    """
    Cohen's κ for `k` categories indexed 0..k-1.
    Linear weights when `weighted=True` (suitable for ordinal scales).
    Returns None if there is no variance (κ undefined).
    """
    if not pairs:
        return None

    n = len(pairs)
    # Observed disagreement matrix
    obs = [[0.0] * k for _ in range(k)]
    for a, b in pairs:
        obs[a][b] += 1
    obs = [[v / n for v in row] for row in obs]

    row_marg = [sum(obs[i]) for i in range(k)]
    col_marg = [sum(obs[i][j] for i in range(k)) for j in range(k)]

    if weighted:
        # Linear (Cicchetti) weights — 1 on the diagonal, decreasing linearly.
        w = [[1 - abs(i - j) / (k - 1) for j in range(k)] for i in range(k)]
    else:
        w = [[1 if i == j else 0 for j in range(k)] for i in range(k)]

    p_o = sum(w[i][j] * obs[i][j] for i in range(k) for j in range(k))
    p_e = sum(w[i][j] * row_marg[i] * col_marg[j] for i in range(k) for j in range(k))

    if abs(1 - p_e) < 1e-12:
        return None  # κ is undefined (perfect marginal agreement → degenerate)
    return (p_o - p_e) / (1 - p_e)


def interpret_kappa(k: float | None) -> str:
    if k is None:
        return "undefined (no variance)"
    for threshold, label in LANDIS_KOCH:
        if k >= threshold:
            return f"κ = {k:+.3f} — {label}"
    return f"κ = {k:+.3f}"


# ── Per-dimension agreement ──────────────────────────────────────────────────

def collect_ordinal_pairs(
    r1: dict[str, dict], r2: dict[str, dict], dim: str
) -> tuple[list[tuple[int, int]], list[str]]:
    """Returns (pairs, disagreement_run_ids)."""
    pairs: list[tuple[int, int]] = []
    disagreements: list[str] = []
    common = sorted(set(r1) & set(r2))
    for rid in common:
        v1 = r1[rid].get(dim)
        v2 = r2[rid].get(dim)
        if v1 not in ORDINAL_MAP or v2 not in ORDINAL_MAP:
            continue
        pairs.append((ORDINAL_MAP[v1], ORDINAL_MAP[v2]))
        if v1 != v2:
            disagreements.append(rid)
    return pairs, disagreements


def hallucination_binary_pairs(
    r1: dict[str, dict], r2: dict[str, dict], category: str
) -> list[tuple[int, int]]:
    """Treat each category as binary (1 = applied, 0 = not applied) per output."""
    pairs: list[tuple[int, int]] = []
    common = sorted(set(r1) & set(r2))
    for rid in common:
        a = 1 if category in (r1[rid].get("hallucination_categories") or []) else 0
        b = 1 if category in (r2[rid].get("hallucination_categories") or []) else 0
        pairs.append((a, b))
    return pairs


def jaccard_per_pair(r1: dict[str, dict], r2: dict[str, dict]) -> list[float]:
    """Per-output Jaccard similarity of the two raters' hallucination sets."""
    out: list[float] = []
    for rid in sorted(set(r1) & set(r2)):
        a = set(r1[rid].get("hallucination_categories") or [])
        b = set(r2[rid].get("hallucination_categories") or [])
        if not a and not b:
            out.append(1.0)  # both empty: full agreement on "none"
        else:
            out.append(len(a & b) / len(a | b) if (a | b) else 1.0)
    return out


# ── Reporting ────────────────────────────────────────────────────────────────

def print_table(title: str, rows: list[dict], columns: list[str]) -> None:
    print()
    print("─" * 90)
    print(f"  {title}")
    print("─" * 90)
    widths = [max(len(c), max((len(str(r.get(c, ""))) for r in rows), default=0)) for c in columns]
    header = "  ".join(c.ljust(w) for c, w in zip(columns, widths))
    print(header)
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(w) for c, w in zip(columns, widths)))


def write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    import csv
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


# ── Main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inter-rater reliability — Cohen's weighted κ per dimension "
                    "and per hallucination category, plus disagreement lists."
    )
    parser.add_argument("--r1", required=True, type=Path,
                        help="Primary rater's experiments.jsonl")
    parser.add_argument("--r2", required=True, type=Path,
                        help="Second rater's experiments file")
    parser.add_argument("--output", default=Path("output/irr"), type=Path,
                        help="Directory to write per-dim disagreement lists + summary CSVs.")
    parser.add_argument("--threshold", type=float, default=0.60,
                        help="κ acceptance threshold (default: 0.60 per §B.8.2).")
    args = parser.parse_args(argv)

    if not args.r1.exists(): print(f"error: {args.r1} not found", file=sys.stderr); return 2
    if not args.r2.exists(): print(f"error: {args.r2} not found", file=sys.stderr); return 2

    rows1 = read_jsonl(args.r1)
    rows2 = read_jsonl(args.r2)
    r1 = index_by_run_id(rows1)
    r2 = index_by_run_id(rows2)
    common = sorted(set(r1) & set(r2))

    print(f"R1 rows : {len(rows1)}  (unique run_ids: {len(r1)})")
    print(f"R2 rows : {len(rows2)}  (unique run_ids: {len(r2)})")
    print(f"common  : {len(common)} run_id(s) rated by both")
    if not common:
        print("error: no overlapping run_ids — nothing to compare.", file=sys.stderr)
        return 2

    # ── Ordinal dimensions: Cohen's weighted κ (linear) ──────────────────────
    ordinal_rows: list[dict] = []
    for dim in ORDINAL_DIMS:
        pairs, disagreements = collect_ordinal_pairs(r1, r2, dim)
        k = cohens_kappa(pairs, k=len(ORDINAL_VALUES), weighted=True)
        ordinal_rows.append({
            "dimension":     dim,
            "n_pairs":       len(pairs),
            "n_disagree":    len(disagreements),
            "kappa":         f"{k:+.3f}" if k is not None else "n/a",
            "interpretation": interpret_kappa(k),
            "accepted":      "yes" if (k is not None and k >= args.threshold) else "no",
        })
        if disagreements:
            write_csv(
                args.output / f"disagreements_{dim}.csv",
                [{"run_id":       rid,
                  "r1":           r1[rid].get(dim),
                  "r2":           r2[rid].get(dim),
                  "r1_rationale": r1[rid].get(f"{dim}_rationale"),
                  "r2_rationale": r2[rid].get(f"{dim}_rationale")}
                 for rid in disagreements],
                columns=["run_id", "r1", "r2", "r1_rationale", "r2_rationale"],
            )

    print_table(
        "Ordinal dimensions — Cohen's weighted κ (linear)",
        ordinal_rows,
        ["dimension", "n_pairs", "n_disagree", "kappa", "interpretation", "accepted"],
    )
    write_csv(args.output / "kappa_ordinal.csv", ordinal_rows,
              ["dimension", "n_pairs", "n_disagree", "kappa", "interpretation", "accepted"])

    # ── Hallucination categories: per-category binary κ + Jaccard ────────────
    hallu_rows: list[dict] = []
    for cat in HALLUCINATION_CATEGORIES:
        pairs = hallucination_binary_pairs(r1, r2, cat)
        k = cohens_kappa(pairs, k=2, weighted=False)
        hallu_rows.append({
            "category":      cat,
            "n_pairs":       len(pairs),
            "r1_count":      sum(a for a, _ in pairs),
            "r2_count":      sum(b for _, b in pairs),
            "kappa":         f"{k:+.3f}" if k is not None else "n/a",
            "interpretation": interpret_kappa(k),
            "accepted":      "yes" if (k is not None and k >= args.threshold) else "no",
        })

    print_table(
        "Hallucination categories — binary κ per category",
        hallu_rows,
        ["category", "n_pairs", "r1_count", "r2_count", "kappa", "interpretation", "accepted"],
    )
    write_csv(args.output / "kappa_hallucination.csv", hallu_rows,
              ["category", "n_pairs", "r1_count", "r2_count", "kappa", "interpretation", "accepted"])

    # ── Multi-label set agreement: mean Jaccard ──────────────────────────────
    jacs = jaccard_per_pair(r1, r2)
    mean_j = sum(jacs) / len(jacs) if jacs else None
    print()
    print(f"  Mean Jaccard agreement on hallucination sets (multi-label, all categories): "
          f"{mean_j:.3f}" if mean_j is not None else "  Mean Jaccard: n/a")

    # ── Quality-attribute counts: simple comparison ──────────────────────────
    qa_diffs = []
    for rid in common:
        a1 = r1[rid].get("attributes_correctly_aligned")
        a2 = r2[rid].get("attributes_correctly_aligned")
        i1 = r1[rid].get("incorrectly_mentioned_attributes")
        i2 = r2[rid].get("incorrectly_mentioned_attributes")
        if None in (a1, a2, i1, i2):
            continue
        qa_diffs.append({
            "run_id": rid,
            "aligned_diff":   a1 - a2,
            "incorrect_diff": i1 - i2,
        })
    if qa_diffs:
        n = len(qa_diffs)
        mean_align = sum(r["aligned_diff"]   for r in qa_diffs) / n
        mean_inc   = sum(r["incorrect_diff"] for r in qa_diffs) / n
        max_align  = max(abs(r["aligned_diff"])   for r in qa_diffs)
        max_inc    = max(abs(r["incorrect_diff"]) for r in qa_diffs)
        print()
        print("─" * 90)
        print("  Quality-attribute counts — R1 − R2 (positive = R1 counted more)")
        print("─" * 90)
        print(f"  aligned   :  n={n}, mean diff = {mean_align:+.2f}, |max diff| = {max_align}")
        print(f"  incorrect :  n={n}, mean diff = {mean_inc:+.2f}, |max diff| = {max_inc}")

    # ── Verdict ──────────────────────────────────────────────────────────────
    bad = [r for r in ordinal_rows if r["accepted"] == "no"]
    if bad:
        print()
        print(f"  WARNING: {len(bad)} dimension(s) below κ ≥ {args.threshold} — invoke §B.9 procedure.")
        for r in bad:
            print(f"    - {r['dimension']}:  {r['interpretation']}")
    else:
        print(f"\n  All ordinal dimensions meet κ ≥ {args.threshold}.")

    print(f"\n  CSVs written to: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
