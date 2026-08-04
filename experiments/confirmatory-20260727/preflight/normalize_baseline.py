from __future__ import annotations

import json
import re
from pathlib import Path

PIPELINE = Path(r"Z:\GitHub\hybrid-static-llm-pipeline")
SOURCE = PIPELINE / "archive" / "previous-runs-20260727" / "runs" / "20260708-095630.jsonl"
OUTPUT = PIPELINE / "experiments" / "confirmatory-20260727" / "confirmatory-baseline.jsonl"
EXCLUDED_SYMBOLS = {"OrderImporter.ImportBatch"}


def declaration_index(record: dict, lines: list[str]) -> int:
    symbol = record["symbol_name"].split(".")[-1]
    if record["anti_pattern_type"] == "god_class":
        pattern = re.compile(rf"\b(?:class|record|struct)\s+{re.escape(symbol)}\b")
    else:
        pattern = re.compile(rf"\b{re.escape(symbol)}\s*(?:<[^>]+>\s*)?\(")
    matches = [i for i, line in enumerate(lines) if pattern.search(line)]
    if len(matches) != 1:
        raise ValueError(f"expected one declaration for {record['symbol_name']}, found {matches}")
    return matches[0]


def main() -> None:
    normalized = []
    audit = []
    for raw in SOURCE.read_text(encoding="utf-8-sig").splitlines():
        if not raw.strip():
            continue
        record = json.loads(raw)
        if record.get("anti_pattern_type") not in {"long_method", "god_class"}:
            continue
        if record.get("symbol_name") in EXCLUDED_SYMBOLS:
            continue
        snippet = (record.get("snippet") or "").replace("\r\n", "\n").strip("\r\n")
        lines = snippet.split("\n")
        start = declaration_index(record, lines)
        declaration = "\n".join(lines[start:])
        record["snippet"] = declaration
        end_line = record["line"] + len(declaration.split("\n")) - 1
        normalized.append(record)
        audit.append({
            "file_path": record["file_path"],
            "symbol_name": record["symbol_name"],
            "anti_pattern_type": record["anti_pattern_type"],
            "leading_trivia_lines_removed": start,
            "target_start_line": record["line"],
            "target_end_line": end_line,
        })
    if len(normalized) != 19:
        raise ValueError(f"expected 19 confirmatory records, found {len(normalized)}")
    OUTPUT.write_text("\n".join(json.dumps(row, separators=(",", ":")) for row in normalized) + "\n", encoding="utf-8", newline="\n")
    (OUTPUT.parent / "preflight" / "BASELINE_NORMALIZATION_AUDIT.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8", newline="\n")

if __name__ == "__main__":
    main()
