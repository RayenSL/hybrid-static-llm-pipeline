"""
Interactive scoring tool — produces `experiments.jsonl` from raw run-traces.

Walks through every (or a sampled subset of) run record in one or more
`runs/*.jsonl` files, displays the prompt and the model's output, and asks
the rater for the dependent-variable scores the thesis evaluates.

The output file is the input to `analyse_results.py`.

Usage:
    python score_runs.py --input ../src/runs/*.jsonl --output experiments.jsonl
    python score_runs.py --input ../src/runs/*.jsonl --output experiments.jsonl --sample 50 --seed 42
    python score_runs.py --input ../src/runs/*.jsonl --output experiments.jsonl \
                         --filter-model gpt-5-mini --filter-context-level relational

Behaviour:
    * Resumable — already-scored `run_id`s are skipped on the next launch.
    * Press Enter to accept a default; type `skip` to skip the row entirely;
      type `quit` to save what you have and exit.
    * Output is JSONL: one row per scored run, identical to the input row plus
      the scoring fields.
"""
from __future__ import annotations

import argparse
import glob as _glob
import json
import random
import sys
import textwrap
from pathlib import Path
from typing import Iterable

# ── Score scales ─────────────────────────────────────────────────────────────

LIKERT_MIN, LIKERT_MAX = 1, 5

HALLUCINATION_TYPES = [
    "",                  # none
    "fabricated_api",    # references API/method that doesn't exist
    "wrong_logic",       # reasoning or refactor is incorrect
    "irrelevant",        # answer doesn't address the finding
    "contradictory",     # internally inconsistent
    "other",
]

SCORE_FIELDS = [
    ("explanation_correctness_score",   "Explanation correctness     (1–5)"),
    ("explanation_completeness_score",  "Explanation completeness    (1–5)"),
    ("explanation_specificity_score",   "Explanation specificity     (1–5)"),
    ("repair_correctness_score",        "Repair correctness          (1–5)"),
    ("repair_actionability_score",      "Repair actionability        (1–5)"),
]
# Note: quality_attribute_alignment is auto-computed by the C# pipeline as 0/1/null
# (lexical match of expected vs mentioned ISO/IEC 25010 attributes), and carried
# through unchanged by the rater. Add free-text notes via `quality_attribute_notes`
# below if you want to qualify or override the auto value.


# ── I/O helpers ──────────────────────────────────────────────────────────────

def expand_inputs(patterns: Iterable[str]) -> list[Path]:
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


def read_already_scored(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()
    seen: set[str] = set()
    with output_path.open("r", encoding="utf-8-sig") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                seen.add(json.loads(raw)["run_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return seen


def append_record(output_path: Path, record: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False))
        fh.write("\n")


# ── Prompts ──────────────────────────────────────────────────────────────────

QUIT, SKIP = object(), object()


def prompt_likert(label: str, default: int | None = None) -> int | object:
    rng = f"{LIKERT_MIN}-{LIKERT_MAX}"
    suffix = f" [default: {default}]" if default is not None else ""
    while True:
        raw = input(f"  {label}{suffix} ({rng}, skip, quit): ").strip().lower()
        if raw == "quit": return QUIT
        if raw == "skip": return SKIP
        if raw == "" and default is not None:
            return default
        try:
            value = int(raw)
        except ValueError:
            print(f"    Expected an integer in {rng}.")
            continue
        if LIKERT_MIN <= value <= LIKERT_MAX:
            return value
        print(f"    Out of range — must be {rng}.")


def prompt_yes_no(label: str, default: bool = True) -> bool | object:
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        raw = input(f"  {label} {suffix}: ").strip().lower()
        if raw == "quit":              return QUIT
        if raw == "skip":              return SKIP
        if raw == "":                  return default
        if raw in ("y", "yes"):        return True
        if raw in ("n", "no"):         return False
        print("    Please answer y or n (or skip / quit).")


def prompt_choice(label: str, options: list[str]) -> str | object:
    print(f"  {label}")
    for i, opt in enumerate(options):
        display = "(none)" if opt == "" else opt
        print(f"    [{i}] {display}")
    while True:
        raw = input("  choice (number, blank = 0/none, skip, quit): ").strip().lower()
        if raw == "quit": return QUIT
        if raw == "skip": return SKIP
        if raw == "":     return options[0]
        try:
            idx = int(raw)
        except ValueError:
            print("    Expected an integer index.")
            continue
        if 0 <= idx < len(options):
            return options[idx]
        print(f"    Out of range — pick 0..{len(options) - 1}")


# ── Display ──────────────────────────────────────────────────────────────────

def show_run(run: dict, index: int, total: int) -> None:
    print()
    print("═" * 100)
    print(f"  [{index}/{total}]   run_id={run.get('run_id', '?')}   "
          f"run_number={run.get('run_number', '?')}")
    print("═" * 100)
    print(f"  Anti-pattern : {run.get('anti_pattern_type')}")
    print(f"  Symbol       : {run.get('symbol_name')}")
    print(f"  Location     : {run.get('file_path')}:{run.get('line')}")
    print(f"  Severity     : {run.get('severity')}")
    print(f"  Model        : {run.get('model_name')}    "
          f"context={run.get('context_level')}    "
          f"prompt={run.get('prompt_version')}")
    if run.get("error_status"):
        print(f"  ERROR        : {run.get('error_status')}  ({run.get('error_message')})")

    expl = run.get("parsed_explanation") or run.get("raw_llm_output") or ""
    repr_ = run.get("parsed_suggested_fix") or ""

    print()
    print("  ── Explanation " + "─" * 84)
    print(_indent(expl, 4))
    if repr_:
        print()
        print("  ── Suggested fix " + "─" * 82)
        print(_indent(repr_, 4))


def _indent(text: str, spaces: int, max_lines: int = 60) -> str:
    text = (text or "").rstrip()
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"… [{len(text.splitlines()) - max_lines} more lines truncated]"]
    pad = " " * spaces
    return "\n".join(pad + ln for ln in lines)


# ── Scoring loop ─────────────────────────────────────────────────────────────

def score_run(run: dict) -> dict | None:
    """Returns the enriched record, or None if the user typed `skip`. Raises StopIteration on `quit`."""
    record = dict(run)  # carry all original fields through

    is_tp = prompt_yes_no("Is this a true positive?", default=True)
    if is_tp is QUIT: raise StopIteration
    if is_tp is SKIP: return None
    record["is_true_positive"] = bool(is_tp)

    for field, label in SCORE_FIELDS:
        value = prompt_likert(label)
        if value is QUIT: raise StopIteration
        if value is SKIP: return None
        record[field] = value

    htype = prompt_choice("Hallucination type", HALLUCINATION_TYPES)
    if htype is QUIT: raise StopIteration
    if htype is SKIP: return None
    record["hallucination_type"] = htype if htype != "" else None

    # Optional free-text qualifier for the auto-computed quality_attribute_alignment.
    expected = run.get("expected_quality_attributes") or []
    mentioned = run.get("llm_quality_attributes_mentioned") or []
    auto_alignment = run.get("quality_attribute_alignment")
    print(f"  quality_attribute_alignment (auto): {auto_alignment}   "
          f"expected={expected}   mentioned={mentioned}")
    notes = input("  quality_attribute_notes (free text, blank to skip): ").strip()
    if notes.lower() == "quit": raise StopIteration
    record["quality_attribute_notes"] = notes if notes else None

    record["success"] = run.get("error_status") is None
    record["parsing_failed"] = run.get("parse_status") == "failed"
    return record


def driver(runs: list[dict], output_path: Path) -> int:
    already = read_already_scored(output_path)
    if already:
        print(f"resuming — {len(already)} run(s) already scored, skipping them.")

    pending = [r for r in runs if r.get("run_id") not in already]
    total = len(pending)

    if total == 0:
        print("nothing to score.")
        return 0

    print(f"scoring {total} run(s) — output: {output_path.resolve()}")
    print("commands:  Enter = accept default | skip = skip row | quit = save and exit")

    scored = 0
    for i, run in enumerate(pending, start=1):
        show_run(run, i, total)
        try:
            record = score_run(run)
        except StopIteration:
            print("\nquit — exiting.")
            break
        if record is None:
            print("  skipped.")
            continue
        append_record(output_path, record)
        scored += 1

    print(f"\ndone — {scored} run(s) appended to {output_path}")
    return 0


# ── Main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Interactive scoring tool — produces experiments.jsonl from raw run-traces.")
    parser.add_argument("--input", "-i", nargs="+", required=True,
                        help="One or more raw run-trace JSONL paths (globs allowed).")
    parser.add_argument("--output", "-o", default=Path("experiments.jsonl"), type=Path,
                        help="Where to append scored rows (default: experiments.jsonl).")
    parser.add_argument("--sample", type=int, default=0,
                        help="Random subsample of N runs (0 = score all).")
    parser.add_argument("--seed", type=int, default=42,
                        help="RNG seed for --sample reproducibility (default: 42).")
    parser.add_argument("--filter-model", default=None,
                        help="Only score runs whose model_name matches this exactly.")
    parser.add_argument("--filter-context-level", default=None,
                        help="Only score runs whose context_level matches this (case-insensitive).")
    parser.add_argument("--filter-anti-pattern", default=None,
                        help="Only score runs whose anti_pattern_type matches this.")
    args = parser.parse_args(argv)

    paths = expand_inputs(args.input)
    if not paths:
        print(f"error: no files matched: {args.input}", file=sys.stderr)
        return 2

    runs = read_runs(paths)
    print(f"loaded {len(runs)} run record(s) from {len(paths)} file(s).")

    # Filters first, then optional sample.
    def keep(r: dict) -> bool:
        if args.filter_model and r.get("model_name") != args.filter_model: return False
        if args.filter_context_level and \
           str(r.get("context_level", "")).lower() != args.filter_context_level.lower(): return False
        if args.filter_anti_pattern and r.get("anti_pattern_type") != args.filter_anti_pattern: return False
        # Exclude obvious junk: empty raw_llm_output AND no parsed text.
        if not (r.get("parsed_explanation") or r.get("raw_llm_output")):
            return False
        return True

    runs = [r for r in runs if keep(r)]
    print(f"after filters: {len(runs)} run(s).")

    if args.sample > 0 and len(runs) > args.sample:
        random.Random(args.seed).shuffle(runs)
        runs = runs[:args.sample]
        print(f"sampled {len(runs)} run(s) (seed={args.seed}).")

    return driver(runs, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
