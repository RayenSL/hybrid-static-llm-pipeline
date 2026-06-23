"""
CLI front-end for the HybridLens run-trace analyser.

Loads one or many `runs/*.jsonl` files and prints the standard thesis tables.
For deeper or custom analyses, import `loader` from a notebook instead.

Usage:
    python compare.py runs/*.jsonl
    python compare.py runs/20260507-final.jsonl runs/20260508-replication.jsonl
    python compare.py runs/*.jsonl --field parsed_suggested_fix
    python compare.py runs/*.jsonl --export-csv ./reports/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

import loader


def _print_section(title: str, frame: pd.DataFrame | pd.Series) -> None:
    print()
    print("─" * 80)
    print(f"  {title}")
    print("─" * 80)
    if isinstance(frame, pd.Series):
        print(frame.to_string())
    else:
        # Friendlier for wide tables in a terminal.
        with pd.option_context(
            "display.max_columns", None,
            "display.width", 160,
            "display.max_colwidth", 80,
        ):
            print(frame.to_string(index=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare and summarise HybridLens run-trace JSONL files."
    )
    parser.add_argument(
        "patterns", nargs="+",
        help="JSONL paths or globs (e.g. runs/*.jsonl)",
    )
    parser.add_argument(
        "--field", default="parsed_explanation",
        choices=["parsed_explanation", "parsed_suggested_fix",
                 "parsed_quality_impact", "parsed_risks"],
        help="Which parsed field to use for similarity / uniqueness analyses.",
    )
    parser.add_argument(
        "--export-csv", metavar="DIR",
        help="Write each table as CSV into DIR (created if missing) in addition to printing.",
    )
    args = parser.parse_args(argv)

    try:
        df = loader.load(*args.patterns)
    except FileNotFoundError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2

    tables: dict[str, pd.DataFrame | pd.Series] = {
        "summary":               loader.summary(df),
        "failure_rates":         loader.failure_rates(df),
        "error_breakdown":       loader.error_breakdown(df),
        "token_cost":            loader.token_cost(df),
        "output_uniqueness":     loader.output_uniqueness(df, field=args.field),
        "run_variance":          loader.run_variance(df, field=args.field),
        "parse_failures":        loader.parse_failures(df),
    }

    for name, table in tables.items():
        _print_section(name, table)

    if args.export_csv:
        out_dir = Path(args.export_csv)
        out_dir.mkdir(parents=True, exist_ok=True)
        for name, table in tables.items():
            path = out_dir / f"{name}.csv"
            if isinstance(table, pd.Series):
                table.to_csv(path, header=["value"])
            else:
                table.to_csv(path, index=False)
        print(f"\nCSV tables written to {out_dir.resolve()}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
