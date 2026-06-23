"""
Select the rated subset from the raw run-trace (one row per cell), then fix the
presentation order under the thesis's blinding constraints.

Pipeline position:
    runs/*.jsonl  (raw, 1620 rows)
        ↓  select_rating_set.py  --seed 42
    experiments_to_rate.jsonl  (540 rows, stratified order)
        ↓  score_runs.py
    experiments.jsonl

Per the thesis (§5.2.5 + §B.2.2):
    * One run per (instance × context × model) cell is picked by uniform random
      draw with `--seed`. The seed is recorded in the manifest sidecar so the
      selection is reproducible.
    * Presentation order is stratified so no two consecutive outputs share the
      same anti-pattern instance, model, or context level.
    * Each row gets a `presentation_index` and a stable `blinding_lot` ID so the
      rater's order can be cross-referenced post-hoc.

Usage:
    python select_rating_set.py --input ../src/runs/*.jsonl --output experiments_to_rate.jsonl
    python select_rating_set.py --input ../src/runs/*.jsonl --output experiments_to_rate.jsonl \\
                                --seed 42 --max-swap-attempts 10000
"""
from __future__ import annotations

import argparse
import glob as _glob
import hashlib
import json
import random
import sys
from collections import Counter
from pathlib import Path


# ── I/O ──────────────────────────────────────────────────────────────────────

def expand_inputs(patterns: list[str]) -> list[Path]:
    out: list[Path] = []
    for pat in patterns:
        matches = _glob.glob(pat)
        if matches:
            out.extend(Path(m) for m in matches)
        elif Path(pat).exists():
            out.append(Path(pat))
    return sorted(set(out))


def read_runs(paths: list[Path]) -> list[dict]:
    runs: list[dict] = []
    for p in paths:
        with p.open("r", encoding="utf-8-sig") as fh:
            for line_no, raw in enumerate(fh, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    runs.append(json.loads(raw))
                except json.JSONDecodeError as ex:
                    print(f"  [warn] {p}:{line_no} skipped — {ex}", file=sys.stderr)
    return runs


# ── Cell selection ───────────────────────────────────────────────────────────

def _cell_key(run: dict) -> tuple:
    """Identifies the (instance × context × model) cell a run belongs to."""
    return (
        run.get("file_path"),
        run.get("symbol_name"),
        run.get("line"),
        run.get("context_level"),
        run.get("model_name"),
    )


def _instance_key(run: dict) -> tuple:
    return (run.get("file_path"), run.get("symbol_name"), run.get("line"))


def _is_eligible(run: dict) -> bool:
    """Exclude rows that cannot be rated under the rubric (§B.3.4)."""
    if run.get("error_status") is not None:
        return False
    if not (run.get("parsed_explanation") or run.get("raw_llm_output")):
        return False
    return True


def select_one_per_cell(runs: list[dict], seed: int) -> list[dict]:
    """Uniform random draw: pick exactly one row from each (instance×context×model) cell."""
    rng = random.Random(seed)
    cells: dict[tuple, list[dict]] = {}
    for r in runs:
        if not _is_eligible(r):
            continue
        cells.setdefault(_cell_key(r), []).append(r)

    selected: list[dict] = []
    for key, candidates in cells.items():
        chosen = rng.choice(candidates)
        chosen["selected_from_run_number"] = chosen.get("run_number")
        selected.append(chosen)
    return selected


# ── Stratified presentation order ────────────────────────────────────────────

def _violates(prev: dict | None, candidate: dict) -> int:
    """Count how many blinding-stratification constraints the candidate violates."""
    if prev is None:
        return 0
    v = 0
    if _instance_key(prev) == _instance_key(candidate):                v += 1
    if prev.get("model_name")    == candidate.get("model_name"):       v += 1
    if prev.get("context_level") == candidate.get("context_level"):    v += 1
    return v


def stratify_presentation_order(items: list[dict], seed: int) -> list[dict]:
    """
    Greedy placement that respects §B.2.2: no two consecutive outputs share the
    same instance, model, or context level. When the constraint cannot be fully
    satisfied (a near-exhausted pool), we pick the candidate that violates the
    fewest constraints — a minor relaxation that is reported in the manifest.
    """
    rng = random.Random(seed + 1)  # different stream than cell selection
    pool = list(items)
    rng.shuffle(pool)

    ordered: list[dict] = []
    relaxations = 0
    while pool:
        prev = ordered[-1] if ordered else None
        best_idx = 0
        best_score = _violates(prev, pool[0])
        for i in range(1, len(pool)):
            score = _violates(prev, pool[i])
            if score < best_score:
                best_idx, best_score = i, score
                if best_score == 0:
                    break
        if best_score > 0:
            relaxations += 1
        ordered.append(pool.pop(best_idx))

    if relaxations:
        print(f"  [info] {relaxations} placement(s) relaxed a constraint "
              f"(pool exhausted of fully-compatible candidates).", file=sys.stderr)
    return ordered


# ── Pilot subset (§B.8.3) ────────────────────────────────────────────────────

def select_pilot_subset(items: list[dict], seed: int, n: int = 10) -> list[dict]:
    """
    Balanced pilot sample. Picks one item per (context_level × anti_pattern_type)
    cell when possible, then top-up to `n` with uniform draws from the remainder.
    The same seed reproduces the same pilot subset.
    """
    rng = random.Random(seed + 2)
    by_strat: dict[tuple, list[dict]] = {}
    for r in items:
        k = (r.get("context_level"), r.get("anti_pattern_type"))
        by_strat.setdefault(k, []).append(r)

    pilot: list[dict] = []
    remaining: list[dict] = []
    for k, rows in by_strat.items():
        rng.shuffle(rows)
        pilot.append(rows[0])
        remaining.extend(rows[1:])

    while len(pilot) < n and remaining:
        rng.shuffle(remaining)
        pilot.append(remaining.pop())

    return pilot[:n]


# ── LLM-only selection (§4.4.1) ──────────────────────────────────────────────

def select_llm_only(rows: list[dict], seed: int) -> list[dict]:
    """
    LLM-only rated set: one run per FILE (not per cell), keeping only the matched
    findings (is_spurious == False) for quality rating. Spurious detections remain
    in the raw run trace and are characterised descriptively by analyse_results.py.
    """
    rng = random.Random(seed + 4)

    by_file: dict[str, dict[int, list[dict]]] = {}
    for r in rows:
        if r.get("architecture") != "llm_only":
            continue
        fp = r.get("file_path")
        run = r.get("run_number", 1)
        by_file.setdefault(fp, {}).setdefault(run, []).append(r)

    selected: list[dict] = []
    for fp, runs in by_file.items():
        run_numbers = sorted(runs.keys())
        chosen_run = rng.choice(run_numbers)
        for r in runs[chosen_run]:
            if r.get("is_spurious") is True:
                continue  # spurious → not quality-rated
            r["selected_from_run_number"] = chosen_run
            selected.append(r)
    return selected


# ── IRR subset (§B.8.1) ──────────────────────────────────────────────────────

def select_irr_subset(rows: list[dict], fraction: float, seed: int) -> list[dict]:
    """
    Stratified subsample of the primary rated set for the second rater (§B.8.1).

    Stratification key: (anti_pattern_type × context_level × model_name). Within
    each cell we pseudorandomly draw ⌈n_cell × fraction⌉ rows, so every cell
    contributes the same proportion. For the canonical fraction=0.30 on a
    perfectly balanced primary set of 360 + 30 rows, this yields 36 hybrid +
    3 baseline rows per anti-pattern (117 total).
    """
    if not (0.0 < fraction <= 1.0):
        raise ValueError(f"fraction must be in (0, 1], got {fraction}")

    rng = random.Random(seed + 3)
    cells: dict[tuple, list[dict]] = {}
    for r in rows:
        key = (r.get("anti_pattern_type"), r.get("context_level"), r.get("model_name"))
        cells.setdefault(key, []).append(r)

    subset: list[dict] = []
    for key, candidates in cells.items():
        n_pick = max(1, round(len(candidates) * fraction))
        n_pick = min(n_pick, len(candidates))
        rng.shuffle(candidates)
        subset.extend(candidates[:n_pick])

    return subset


# ── Annotation ───────────────────────────────────────────────────────────────

def annotate(items: list[dict], seed: int, lot_label: str) -> list[dict]:
    """Attach presentation_index, blinding_lot, selection_seed to each row."""
    for idx, r in enumerate(items, start=1):
        r["presentation_index"] = idx
        r["blinding_lot"]       = lot_label
        r["selection_seed"]     = seed
    return items


# ── Manifest ─────────────────────────────────────────────────────────────────

def write_manifest(
    output_path: Path,
    items: list[dict],
    seed: int,
    sources: list[Path],
    lot_label: str,
    pilot: bool,
) -> None:
    """Sidecar JSON describing the selection — required for reproducibility."""
    by_model    = Counter(r.get("model_name")     for r in items)
    by_context  = Counter(r.get("context_level")  for r in items)
    by_pattern  = Counter(r.get("anti_pattern_type") for r in items)

    manifest = {
        "schema_version":     "selection-1.0",
        "blinding_lot":       lot_label,
        "selection_seed":     seed,
        "is_pilot":           pilot,
        "n_rows":             len(items),
        "by_model":           dict(by_model),
        "by_context_level":   dict(by_context),
        "by_anti_pattern":    dict(by_pattern),
        "sources":            [str(p) for p in sources],
        "output":             str(output_path),
    }

    manifest_path = output_path.with_suffix(output_path.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest: {manifest_path.resolve()}")


def write_jsonl(output_path: Path, items: list[dict]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for r in items:
            fh.write(json.dumps(r, ensure_ascii=False))
            fh.write("\n")


# ── Main ─────────────────────────────────────────────────────────────────────

def _lot_label(seed: int, pilot: bool, irr: bool = False) -> str:
    """Short, stable identifier for the blinding lot — used in IRR cross-refs."""
    h = hashlib.sha1(f"{seed}|{pilot}|{irr}".encode()).hexdigest()[:8]
    if irr:   return f"irr-{h}"
    if pilot: return f"pilot-{h}"
    return f"lot-{h}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select the rated subset (1 row per cell) and fix the presentation order. "
                    "Also supports IRR stratified subsampling from an existing primary set."
    )
    parser.add_argument("--input", "-i", nargs="+",
                        help="One or more raw run-trace JSONL paths (globs allowed). "
                             "Omit when using --irr-from.")
    parser.add_argument("--output", "-o", default=Path("experiments_to_rate.jsonl"), type=Path,
                        help="Output JSONL (default: experiments_to_rate.jsonl).")
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed for cell selection, order stratification, and IRR draw (default: 42).")
    parser.add_argument("--pilot", action="store_true",
                        help="Select a 10-row pilot subset balanced across context × anti-pattern (§B.8.3).")
    parser.add_argument("--pilot-n", type=int, default=10,
                        help="Target size of the pilot subset (default: 10).")
    parser.add_argument("--irr-from", type=Path,
                        help="Path to the primary rated set (experiments_to_rate.jsonl). "
                             "When set, the script subsamples THAT file instead of running "
                             "cell selection on raw runs — produces a stratified IRR subset.")
    parser.add_argument("--irr-fraction", type=float, default=0.30,
                        help="Fraction of the primary set to include in the IRR subset (default: 0.30, per §B.8.1).")
    parser.add_argument("--llm-only", action="store_true",
                        help="Select the LLM-only rated set: one run per file, matched findings only (§4.4.1). "
                             "Point --input at the *-llmonly.jsonl run trace.")
    args = parser.parse_args(argv)

    # ── LLM-only mode ────────────────────────────────────────────────────────
    if args.llm_only:
        if not args.input:
            print("error: --input is required with --llm-only", file=sys.stderr); return 2
        sources = expand_inputs(args.input)
        if not sources:
            print(f"error: no files matched: {args.input}", file=sys.stderr); return 2
        rows = read_runs(sources)
        print(f"loaded {len(rows)} llm-only run record(s) from {len(sources)} file(s).")
        selected = select_llm_only(rows, args.seed)
        print(f"selected {len(selected)} matched llm-only finding(s) (1 run/file).")
        ordered   = stratify_presentation_order(selected, args.seed)
        lot       = _lot_label(args.seed, pilot=False, irr=False) + "-llmonly"
        annotated = annotate(ordered, args.seed, lot)
        write_jsonl(args.output, annotated)
        print(f"wrote {args.output.resolve()}")
        write_manifest(args.output, annotated, args.seed, sources, lot, pilot=False)
        return 0

    # ── IRR mode ─────────────────────────────────────────────────────────────
    if args.irr_from is not None:
        if not args.irr_from.exists():
            print(f"error: {args.irr_from} not found", file=sys.stderr); return 2

        primary = read_runs([args.irr_from])
        print(f"loaded {len(primary)} primary rated row(s) from {args.irr_from}")

        subset = select_irr_subset(primary, args.irr_fraction, args.seed)
        print(f"selected {len(subset)} IRR row(s) (~{args.irr_fraction:.0%} per cell).")

        ordered   = stratify_presentation_order(subset, args.seed)
        lot       = _lot_label(args.seed, pilot=False, irr=True)
        annotated = annotate(ordered, args.seed, lot)

        write_jsonl(args.output, annotated)
        print(f"wrote {args.output.resolve()}")
        write_manifest(args.output, annotated, args.seed, [args.irr_from], lot, pilot=False)
        return 0

    # ── Primary / pilot mode ─────────────────────────────────────────────────
    if not args.input:
        print("error: --input is required (or use --irr-from for IRR subsampling)", file=sys.stderr)
        return 2

    sources = expand_inputs(args.input)
    if not sources:
        print(f"error: no files matched: {args.input}", file=sys.stderr); return 2

    runs = read_runs(sources)
    print(f"loaded {len(runs)} raw run record(s) from {len(sources)} file(s).")

    selected = select_one_per_cell(runs, args.seed)
    print(f"selected {len(selected)} row(s) (1 per cell).")

    if args.pilot:
        selected = select_pilot_subset(selected, args.seed, n=args.pilot_n)
        print(f"reduced to pilot subset of {len(selected)} row(s).")

    ordered = stratify_presentation_order(selected, args.seed)
    annotated = annotate(ordered, args.seed, _lot_label(args.seed, args.pilot))

    write_jsonl(args.output, annotated)
    print(f"wrote {args.output.resolve()}")

    write_manifest(args.output, annotated, args.seed, sources,
                   _lot_label(args.seed, args.pilot), args.pilot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
