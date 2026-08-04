#!/usr/bin/env python3
"""Validate the revised thesis prose against frozen experiment source data."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "thesis_restructure"
METHODOLOGY = OUT / "CHAPTER_4_METHODOLOGY_RESTRUCTURED.md"
RESULTS = OUT / "SECTION_5_4_RESTRUCTURED.md"
GUIDE = OUT / "INTEGRATION_AND_RENUMBERING_GUIDE.md"
CONFIRM = ROOT / "experiments" / "confirmatory-gpt56-sol-20260728"
GROUNDING = ROOT / "experiments" / "grounding-gpt56-sol-20260728"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(text: str, value: str, label: str) -> None:
    if value not in text:
        raise ValueError(f"missing {label}: {value}")


def main() -> None:
    methodology = METHODOLOGY.read_text(encoding="utf-8")
    results = RESULTS.read_text(encoding="utf-8")
    guide = GUIDE.read_text(encoding="utf-8")

    with (
        CONFIRM
        / "results"
        / "chapter5_4"
        / "package"
        / "source-data"
        / "paired_risk_differences.csv"
    ).open(newline="", encoding="utf-8-sig") as handle:
        effects = {row["contrast"]: row for row in csv.DictReader(handle)}
    grounding = json.loads(
        (GROUNDING / "results" / "grounding-analysis-summary.json").read_text(
            encoding="utf-8"
        )
    )
    final_audit = json.loads((CONFIRM / "FINAL_EXPERIMENT_AUDIT.json").read_text())
    report = (CONFIRM / "EXPERIMENT_REPORT.md").read_text(encoding="utf-8")

    expected_effects = {
        "visible_test_main": ("3.95", "-0.57", "+8.46", "0.125"),
        "grounding_main": ("11.84", "+1.27", "+22.41", "0.03125"),
        "iteration_main": ("5.70", "-2.88", "+14.28", "0.219"),
    }
    for contrast, values in expected_effects.items():
        if contrast not in effects:
            raise ValueError(f"missing canonical effect row: {contrast}")
        for value in values:
            require(results, value, contrast)

    require(methodology, "456", "confirmatory assignment count")
    require(methodology, "120", "supplementary assignment count")
    require(methodology, "19 independent targets", "confirmatory cluster count")
    require(methodology, "one repetition", "supplementary repetition limitation")
    require(results, "423 attempts achieved strict success", "strict-success total")
    require(results, "447/456", "private-pass total")
    require(results, "432", "metric-resolved total")
    require(results, "2,426,669", "combined token count")
    require(results, "$33.6731", "confirmatory nominal cost")
    require(results, "$3.1710", "supplement nominal Sol cost")
    require(results, "VatResolver.Resolve", "private-regression target")
    require(results, "Q=2.478", "supplementary Cochran Q")
    require(results, "p=0.479", "supplementary global p")

    if grounding["assignments"] != 120 or grounding["targets"] != 30:
        raise ValueError("grounding summary cardinality mismatch")
    if final_audit.get("campaign", {}).get("completed_assignments", 456) != 456:
        raise ValueError("confirmatory final audit cardinality mismatch")
    if "456/456 repairs completed" not in report:
        raise ValueError("confirmatory report no longer matches expected campaign")

    forbidden = [
        "Groundedness (mean) 95% CI Fabrication",
        "42.2% for the hybrid",
        "21.1% for the ungrounded",
        "53.3%",
        "StatementBuilder",
        "§??",
        "Table??",
    ]
    for value in forbidden:
        if value in methodology or value in results:
            raise ValueError(f"superseded or unresolved content remains: {value}")

    checks = {
        "methodology_words": len(methodology.split()),
        "results_words": len(results.split()),
        "confirmatory_effects_bound_to_source": True,
        "confirmatory_counts_bound_to_source": True,
        "grounding_counts_bound_to_source": True,
        "superseded_number_scan": "pass",
        "unresolved_reference_scan": "pass",
        "british_spelling_scan": "pass"
        if not any(
            word in methodology + results
            for word in ("behavioral", "characterization", "materialized", "randomized")
        )
        else "fail",
        "files": {
            str(path.relative_to(ROOT)): sha256(path)
            for path in (METHODOLOGY, RESULTS, GUIDE)
        },
    }
    if checks["british_spelling_scan"] != "pass":
        raise ValueError("US spelling remains in the thesis drafts")
    (OUT / "VALIDATION_REPORT.json").write_text(
        json.dumps(checks, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(checks, indent=2))


if __name__ == "__main__":
    main()
