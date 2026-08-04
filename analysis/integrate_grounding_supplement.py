#!/usr/bin/env python3
"""Integrate the separately frozen grounding supplement into Chapter 5.4."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments" / "grounding-gpt56-sol-20260728"
PACKAGE = EXPERIMENT / "results" / "package"
OUTPUT = ROOT / "output" / "chapter5_4"

MAPPING = [
    {
        "Original context level": "Minimal",
        "Original thesis payload": "Detected code fragment only",
        "GPT-5.6 Sol status": "Run in the separate four-level grounding supplement",
        "Relationship to frozen Sol factor": (
            "No direct binary-factor equivalent; result reported in Table 5.9b"
        ),
    },
    {
        "Original context level": "Structural",
        "Original thesis payload": (
            "Minimal plus symbol, file/line location, anti-pattern type, and metrics"
        ),
        "GPT-5.6 Sol status": (
            "Approximated by the confirmatory grounding addition and run separately"
        ),
        "Relationship to frozen Sol factor": "Supplement result reported in Table 5.9b",
    },
    {
        "Original context level": "Relational",
        "Original thesis payload": (
            "Structural plus surrounding code and enclosing class/member summary"
        ),
        "GPT-5.6 Sol status": "Run in the separate four-level grounding supplement",
        "Relationship to frozen Sol factor": "Supplement result reported in Table 5.9b",
    },
    {
        "Original context level": "Full",
        "Original thesis payload": (
            "All prior elements plus project metadata and additional same-file findings"
        ),
        "GPT-5.6 Sol status": "Run in the separate four-level grounding supplement",
        "Relationship to frozen Sol factor": (
            "Used frozen project metadata; co-located findings were absent because "
            "each target occupied a unique file"
        ),
    },
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def markdown_table(rows: list[dict]) -> str:
    fields = list(rows[0])
    lines = [
        "| " + " | ".join(fields) + " |",
        "|" + "|".join("---" for _ in fields) + "|",
    ]
    lines.extend(
        "| " + " | ".join(str(row[field]) for field in fields) + " |" for row in rows
    )
    return "\n".join(lines) + "\n"


def latex_escape(value: object) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(character, character) for character in str(value))


def write_mapping() -> None:
    stem = OUTPUT / "tables" / "table5_9a_context_grounding_correspondence"
    fields = list(MAPPING[0])
    with stem.with_suffix(".csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(MAPPING)
    stem.with_suffix(".md").write_text(markdown_table(MAPPING), encoding="utf-8")
    latex = [
        r"\begin{tabular}{llll}",
        r"\toprule",
        " & ".join(latex_escape(field) for field in fields) + r" \\",
        r"\midrule",
        *[
            " & ".join(latex_escape(row[field]) for field in fields) + r" \\"
            for row in MAPPING
        ],
        r"\bottomrule",
        r"\end{tabular}",
        "",
    ]
    stem.with_suffix(".tex").write_text("\n".join(latex), encoding="utf-8")


def copy_supplement() -> None:
    for name in (
        "table5_9b_four_level_grounding_results",
        "table5_9c_grounding_matched_inference",
        "table5_9d_grounding_tokens_cost",
    ):
        for extension in ("csv", "md", "tex"):
            source = PACKAGE / "tables" / f"{name}.{extension}"
            shutil.copy2(source, OUTPUT / "tables" / source.name)
    for extension in ("png", "svg", "pdf"):
        source = PACKAGE / "figures" / f"figure5_9_grounding_context_effect.{extension}"
        shutil.copy2(source, OUTPUT / "figures" / source.name)


def integrate_tables() -> None:
    path = OUTPUT / "CHAPTER_5_4_TABLES.md"
    text = path.read_text(encoding="utf-8")
    heading = (
        "### Table 5.9a: Correspondence between the original four context levels "
        "and the frozen Sol grounding factor"
    )
    start = text.index(heading)
    end = text.index("### Table 5.9: Pre-repair", start)
    section = (
        heading
        + "\n\n"
        + markdown_table(MAPPING)
        + "\n### Table 5.9b: Separate matched four-level grounding experiment\n\n"
        + (OUTPUT / "tables" / "table5_9b_four_level_grounding_results.md").read_text(
            encoding="utf-8"
        )
        + "\nThe global matched comparison was not statistically significant "
        "(Cochran's Q = 2.478, df = 3, p = 0.479). Exact adjacent McNemar tests "
        "also found no evidence of differences after Holm adjustment; all three "
        "adjusted p-values were 1. This one-repetition supplement is resource-"
        "constrained evidence and does not extend the confirmatory factorial.\n\n"
        "### Table 5.9c: Matched inference for the separate grounding experiment\n\n"
        + (OUTPUT / "tables" / "table5_9c_grounding_matched_inference.md").read_text(
            encoding="utf-8"
        )
        + "\n### Table 5.9d: Grounding token consumption and nominal Sol cost\n\n"
        + (OUTPUT / "tables" / "table5_9d_grounding_tokens_cost.md").read_text(
            encoding="utf-8"
        )
        + "\n"
    )
    path.write_text(text[:start] + section + text[end:], encoding="utf-8")


def integrate_manifest() -> None:
    path = OUTPUT / "CHAPTER_5_4_REPLACEMENT_MANIFEST.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "plus supplemental Table 5.9a, are provided as CSV, Markdown, and LaTeX;\n"
        "Figures 5.2-5.8 are provided as PNG, SVG, and PDF.",
        "plus supplemental Tables 5.9a-5.9d, are provided as CSV, Markdown, and "
        "LaTeX;\nFigures 5.2-5.9 are provided as PNG, SVG, and PDF.",
    )
    old = (
        "- Supplemental Table 5.9a preserves the Minimal/Structural/Relational/Full taxonomy\n"
        "  and states its correspondence to the Sol binary-grounding factor. Relational and\n"
        "  Full are explicitly marked not run; no Sol outcomes are imputed for them.\n"
        "- Tables 5.9 and 5.10 now report characterization-test generation/admission and\n"
        "  test-ON exposure fidelity; the retired four-level context factor is not fabricated."
    )
    new = (
        "- Supplemental Table 5.9a preserves the Minimal/Structural/Relational/Full taxonomy\n"
        "  and distinguishes it from the confirmatory binary grounding factor.\n"
        "- Supplemental Tables 5.9b-5.9d and Figure 5.9 report a separately frozen,\n"
        "  one-repetition matched experiment over all 30 targets. Its denominators and\n"
        "  conclusions do not alter the completed confirmatory factorial.\n"
        "- Tables 5.9 and 5.10 continue to report characterization-test generation/admission\n"
        "  and test-ON exposure fidelity for the confirmatory factorial."
    )
    if old not in text:
        raise ValueError("replacement-manifest integration marker not found")
    path.write_text(text.replace(old, new), encoding="utf-8")


def integrate_captions() -> None:
    path = OUTPUT / "CHAPTER_5_4_FIGURE_CAPTIONS.md"
    text = path.read_text(encoding="utf-8")
    caption = (
        "- **Figure 5.9.** Detector-verified and behavior-preserving repair rates in the\n"
        "  separately frozen Minimal/Structural/Relational/Full grounding experiment.\n"
        "  Error bars show 95% Wilson intervals; matched inference uses Cochran's Q and\n"
        "  exact adjacent McNemar tests with Holm adjustment.\n"
    )
    if "**Figure 5.9.**" not in text:
        text += caption
    path.write_text(text, encoding="utf-8")


def seal() -> None:
    targets = [
        OUTPUT / "CHAPTER_5_4_TABLES.md",
        OUTPUT / "CHAPTER_5_4_FIGURE_CAPTIONS.md",
        OUTPUT / "CHAPTER_5_4_REPLACEMENT_MANIFEST.md",
        OUTPUT / "GROUNDING_SUPPLEMENT.md",
        *sorted((OUTPUT / "tables").glob("table5_9[abcd]*")),
        *sorted((OUTPUT / "figures").glob("figure5_9_grounding_context_effect.*")),
        *sorted((OUTPUT / "source-data").glob("grounding_*")),
        OUTPUT / "source-data" / "figure5_9_grounding_context_effect.csv",
        EXPERIMENT / "POST_REPAIR_AUDIT.json",
        EXPERIMENT / "POST_PRIVATE_AUDIT.json",
        EXPERIMENT / "results" / "grounding-analysis-summary.json",
    ]
    unique = sorted(set(targets))
    for path in unique:
        if not path.is_file():
            raise FileNotFoundError(path)
    checksum_path = EXPERIMENT / "FINAL_RESULTS_SHA256SUMS.txt"
    checksum_path.write_text(
        "".join(f"{sha256(path)}  {path.relative_to(ROOT).as_posix()}\n" for path in unique),
        encoding="utf-8",
        newline="\n",
    )
    audit = {
        "status": "grounding_experiment_complete",
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_id": "eb160df37c8996164a8730c0",
        "assignments": 120,
        "contexts": 4,
        "targets": 30,
        "chapter54_integration": True,
        "confirmatory_package_modified": False,
        "final_checksum_entries": len(unique),
        "final_checksum_ledger_sha256": sha256(checksum_path),
    }
    (EXPERIMENT / "FINAL_RESULTS_AUDIT.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> None:
    copy_supplement()
    write_mapping()
    integrate_tables()
    integrate_manifest()
    integrate_captions()
    seal()
    print("grounding supplement integrated and sealed")


if __name__ == "__main__":
    main()
