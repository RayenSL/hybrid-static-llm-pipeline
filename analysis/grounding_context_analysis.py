#!/usr/bin/env python3
"""Analyze and package the frozen GPT-5.6 Sol four-level grounding experiment."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import math
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path


LEVELS = ["minimal", "structural", "relational", "full"]
LEVEL_LABEL = {level: level.title() for level in LEVELS}
PATTERN_LABEL = {
    "god_class": "God Class",
    "long_method": "Long Method",
    "obsolete_api_usage": "Obsolete API Usage",
}
KNOWN_ATTRIBUTES = [
    "maintainability",
    "modularity",
    "analysability",
    "analyzability",
    "modifiability",
    "testability",
    "security",
    "reliability",
    "compatibility",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def local_path(raw: str) -> Path:
    normalized = raw.replace("\\", "/")
    if len(normalized) >= 3 and normalized[1:3] == ":/":
        return Path("/mnt") / normalized[0].lower() / normalized[3:]
    return Path(normalized)


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def regularized_gamma_q(a: float, x: float) -> float:
    """Numerical Recipes regularized upper incomplete gamma Q(a, x)."""
    if x < 0 or a <= 0:
        raise ValueError("invalid gamma arguments")
    if x == 0:
        return 1.0
    eps = 3e-14
    tiny = 1e-300
    max_iter = 10000
    log_term = -x + a * math.log(x) - math.lgamma(a)
    if x < a + 1:
        ap = a
        total = 1.0 / a
        delta = total
        for _ in range(max_iter):
            ap += 1
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * eps:
                return max(0.0, min(1.0, 1.0 - total * math.exp(log_term)))
        raise RuntimeError("gamma series did not converge")
    b = x + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, max_iter + 1):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < eps:
            return max(0.0, min(1.0, math.exp(log_term) * h))
    raise RuntimeError("gamma continued fraction did not converge")


def cochran_q(matrix: list[list[int]]) -> tuple[float, int, float]:
    n = len(matrix)
    k = len(matrix[0])
    if any(len(row) != k for row in matrix):
        raise ValueError("ragged matched matrix")
    column_sums = [sum(matrix[i][j] for i in range(n)) for j in range(k)]
    row_sums = [sum(row) for row in matrix]
    total = sum(column_sums)
    denominator = k * total - sum(value * value for value in row_sums)
    if denominator == 0:
        return 0.0, k - 1, 1.0
    statistic = (k - 1) * (k * sum(value * value for value in column_sums) - total * total)
    statistic /= denominator
    return statistic, k - 1, regularized_gamma_q((k - 1) / 2, statistic / 2)


def exact_mcnemar(left: list[int], right: list[int]) -> tuple[int, int, float]:
    left_only = sum(a == 1 and b == 0 for a, b in zip(left, right))
    right_only = sum(a == 0 and b == 1 for a, b in zip(left, right))
    discordant = left_only + right_only
    if discordant == 0:
        return left_only, right_only, 1.0
    low = min(left_only, right_only)
    tail = sum(math.comb(discordant, value) for value in range(low + 1)) / (2**discordant)
    return left_only, right_only, min(1.0, 2 * tail)


def bootstrap_paired_rd(
    lower: list[int], higher: list[int], seed: int, repetitions: int = 20000
) -> tuple[float, float, float]:
    differences = [b - a for a, b in zip(lower, higher)]
    estimate = sum(differences) / len(differences)
    if len(set(differences)) == 1:
        return estimate, estimate, estimate
    generator = random.Random(seed)
    sampled = sorted(
        sum(differences[generator.randrange(len(differences))] for _ in differences)
        / len(differences)
        for _ in range(repetitions)
    )
    lo = sampled[int(0.025 * repetitions)]
    hi = sampled[min(repetitions - 1, int(0.975 * repetitions))]
    return estimate, lo, hi


def holm_adjust(p_values: list[float]) -> list[float]:
    indexed = sorted(enumerate(p_values), key=lambda pair: pair[1])
    adjusted = [0.0] * len(p_values)
    running = 0.0
    m = len(p_values)
    for rank, (original_index, value) in enumerate(indexed):
        running = max(running, min(1.0, (m - rank) * value))
        adjusted[original_index] = running
    return adjusted


def expected_present(text: str, attribute: str) -> bool:
    lowered = text.lower()
    canonical = attribute.lower()
    if canonical == "analysability":
        return "analysability" in lowered or "analyzability" in lowered
    return canonical in lowered


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"refusing to write empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(rows: list[dict]) -> str:
    fields = list(rows[0])
    lines = [
        "| " + " | ".join(fields) + " |",
        "|" + "|".join("---" for _ in fields) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row[field]) for field in fields) + " |")
    return "\n".join(lines) + "\n"


def latex_escape(value: object) -> str:
    text = str(value)
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
    return "".join(replacements.get(char, char) for char in text)


def latex_table(rows: list[dict]) -> str:
    fields = list(rows[0])
    alignment = "l" + "r" * (len(fields) - 1)
    body = [
        rf"\begin{{tabular}}{{{alignment}}}",
        r"\toprule",
        " & ".join(latex_escape(field) for field in fields) + r" \\",
        r"\midrule",
    ]
    body.extend(
        " & ".join(latex_escape(row[field]) for field in fields) + r" \\" for row in rows
    )
    body.extend([r"\bottomrule", r"\end{tabular}"])
    return "\n".join(body) + "\n"


def write_table_variants(directory: Path, stem: str, rows: list[dict]) -> None:
    write_csv(directory / f"{stem}.csv", rows)
    (directory / f"{stem}.md").write_text(markdown_table(rows), encoding="utf-8")
    (directory / f"{stem}.tex").write_text(latex_table(rows), encoding="utf-8")


def figure_svg(rows: list[dict], path: Path) -> None:
    width, height = 1120, 620
    left, right, top, bottom = 210, 72, 126, 94
    plot_width = width - left - right
    row_height = (height - top - bottom) / 4
    teal, purple = "#2a8580", "#6f4c9b"
    ink, muted, grid = "#1a1a1a", "#66707a", "#d9dee2"
    elements = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#1a1a1a}'
        '.title{font-size:24px;font-weight:700}.subtitle{font-size:14px;fill:#66707a}'
        '.axis{font-size:13px;fill:#66707a}.label{font-size:16px;font-weight:700}'
        '.value{font-size:13px;font-weight:700}.legend{font-size:13px}</style>',
        '<text class="title" x="560" y="38" text-anchor="middle">'
        "Grounding context and repair effectiveness</text>",
        '<text class="subtitle" x="560" y="65" text-anchor="middle">'
        "One matched GPT-5.6 Sol observation per target and level (30 targets; 120 calls)</text>",
    ]
    for tick in range(0, 101, 20):
        x = left + plot_width * tick / 100
        elements.append(
            f'<line x1="{x:.1f}" y1="{top-10}" x2="{x:.1f}" y2="{height-bottom}" '
            f'stroke="{grid}" stroke-width="1"/>'
        )
        elements.append(
            f'<text class="axis" x="{x:.1f}" y="{height-bottom+28}" '
            f'text-anchor="middle">{tick}%</text>'
        )
    elements.append(
        f'<text class="axis" x="{left+plot_width/2:.1f}" y="{height-22}" '
        'text-anchor="middle">Percentage of all 30 targets</text>'
    )
    for index, row in enumerate(rows):
        centre = top + row_height * (index + 0.5)
        elements.append(
            f'<text class="label" x="{left-22}" y="{centre+5:.1f}" '
            f'text-anchor="end">{html.escape(row["Context"])}</text>'
        )
        series = [
            ("verified_rate", "verified_lo", "verified_hi", teal, centre - 17),
            ("preserved_rate", "preserved_lo", "preserved_hi", purple, centre + 17),
        ]
        for rate_key, lo_key, hi_key, color, y in series:
            rate = float(row[rate_key])
            lo = float(row[lo_key])
            hi = float(row[hi_key])
            bar_width = plot_width * rate / 100
            x_lo = left + plot_width * lo / 100
            x_hi = left + plot_width * hi / 100
            elements.append(
                f'<rect x="{left}" y="{y-10:.1f}" width="{bar_width:.1f}" height="20" '
                f'fill="{color}" opacity="0.92"/>'
            )
            elements.append(
                f'<line x1="{x_lo:.1f}" y1="{y:.1f}" x2="{x_hi:.1f}" y2="{y:.1f}" '
                f'stroke="{ink}" stroke-width="1.4"/>'
            )
            for cap_x in (x_lo, x_hi):
                elements.append(
                    f'<line x1="{cap_x:.1f}" y1="{y-5:.1f}" x2="{cap_x:.1f}" '
                    f'y2="{y+5:.1f}" stroke="{ink}" stroke-width="1.4"/>'
                )
            label_x = left + bar_width + 8
            anchor = "start"
            if rate > 88:
                label_x = left + bar_width - 8
                anchor = "end"
            elements.append(
                f'<text class="value" x="{label_x:.1f}" y="{y+5:.1f}" '
                f'text-anchor="{anchor}">{rate:.1f}%</text>'
            )
    elements.extend(
        [
            f'<rect x="{left}" y="88" width="18" height="12" fill="{teal}"/>',
            f'<text class="legend" x="{left+26}" y="99">Detector-verified repair</text>',
            f'<rect x="{left+238}" y="88" width="18" height="12" fill="{purple}"/>',
            f'<text class="legend" x="{left+264}" y="99">'
            "Detector-verified + private oracle passed</text>",
            '<text class="subtitle" x="560" y="606" text-anchor="middle">'
            "Error bars are 95% Wilson intervals; inferential tests use the matched target design.</text>",
            "</svg>",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(elements) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True, type=Path)
    parser.add_argument("--public-output", required=True, type=Path)
    args = parser.parse_args()
    experiment = args.experiment.resolve()
    results = experiment / "results"
    package = results / "package"
    tables_dir = package / "tables"
    figures_dir = package / "figures"
    source_dir = package / "source-data"
    for directory in (tables_dir, figures_dir, source_dir):
        directory.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((experiment / "grounding-manifest.json").read_text(encoding="utf-8"))
    assignments = {row["assignment_id"]: row for row in manifest["assignments"]}
    ledger = read_jsonl(experiment / "campaign" / "execution-ledger.jsonl")
    private_rows = {
        row["artifact_id"]: row
        for row in read_jsonl(experiment / "private-results" / "layer3-campaign.jsonl")
    }
    quality_rows = {
        row["assignment_id"]: row
        for row in read_jsonl(results / "quality-rescore.jsonl")
    }

    attempts = []
    by_block: dict[str, dict[str, dict]] = defaultdict(dict)
    for execution in sorted(ledger, key=lambda row: row["order"]):
        assignment = assignments[execution["assignment_id"]]
        trace_path = local_path(execution["trace_file"])
        records = read_jsonl(trace_path)
        generation, verification = records
        artifact_id = None
        private = None
        ref = verification.get("materialized_source_ref")
        if ref:
            artifact = json.loads(local_path(ref).read_text(encoding="utf-8"))
            artifact_id = artifact["artifact_id"]
            private = private_rows[artifact_id]
        quality = quality_rows.get(execution["assignment_id"])
        prose = " ".join(
            value or ""
            for value in (
                generation.get("parsed_explanation"),
                generation.get("parsed_quality_impact"),
            )
        )
        expected = assignment["expected_quality_attributes"]
        mentioned = sorted(
            attribute for attribute in KNOWN_ATTRIBUTES if attribute in prose.lower()
        )
        at_least_one_expected = any(expected_present(prose, item) for item in expected)
        all_expected = all(expected_present(prose, item) for item in expected)
        verified = bool(verification.get("verified_repair_success"))
        private_pass = bool(private and private["evaluated"] and private["passed"])
        row = {
            "order": execution["order"],
            "assignment_id": execution["assignment_id"],
            "block_id": assignment["block_id"],
            "context_level": assignment["context_level"],
            "anti_pattern_type": assignment["anti_pattern_type"],
            "symbol_name": assignment["symbol_name"],
            "verified_repair_ladder": verification["verified_repair_ladder"],
            "verified_repair_success": verified,
            "repair_applicable": bool(verification.get("repair_applicable")),
            "build_passed": verification.get("build_passed"),
            "materialized_artifact_id": artifact_id,
            "private_evaluated": private["evaluated"] if private else False,
            "private_passed": private["passed"] if private and private["evaluated"] else None,
            "private_not_run_reason": private["not_run_reason"] if private else None,
            "behavior_preserving_verified": verified and private_pass,
            "generation_input_tokens": int(generation.get("input_tokens") or 0),
            "generation_output_tokens": int(generation.get("output_tokens") or 0),
            "generation_duration_ms": float(generation.get("duration_ms") or 0),
            "applier_input_tokens": int(verification.get("input_tokens") or 0),
            "applier_output_tokens": int(verification.get("output_tokens") or 0),
            "applier_duration_ms": float(verification.get("duration_ms") or 0),
            "prompt_characters": len(generation["raw_user_prompt"]),
            "nominal_sol_cost_usd": (
                int(generation.get("input_tokens") or 0) * 5
                + int(generation.get("output_tokens") or 0) * 30
            )
            / 1_000_000,
            "quality_attributes_mentioned": mentioned,
            "at_least_one_expected_attribute": at_least_one_expected,
            "all_expected_attributes": all_expected,
            "smell_total_delta": (
                quality["quality_delta"]["smell_total_delta"] if quality else None
            ),
            "ca_headline_total_delta": (
                quality["quality_delta"]["ca_headline_total_delta"] if quality else None
            ),
            "ca_all_total_delta": (
                quality["quality_delta"]["ca_all_total_delta"] if quality else None
            ),
        }
        attempts.append(row)
        by_block[assignment["block_id"]][assignment["context_level"]] = row

    if len(attempts) != 120 or any(set(values) != set(LEVELS) for values in by_block.values()):
        raise ValueError("incomplete 30 x 4 matched attempt matrix")

    attempts_json = source_dir / "grounding_attempts.json"
    attempts_json.write_text(json.dumps(attempts, indent=2) + "\n", encoding="utf-8")
    attempts_csv = [
        {key: json.dumps(value) if isinstance(value, list) else value for key, value in row.items()}
        for row in attempts
    ]
    write_csv(source_dir / "grounding_attempts.csv", attempts_csv)

    matrix = [
        [int(by_block[block][level]["verified_repair_success"]) for level in LEVELS]
        for block in sorted(by_block)
    ]
    q_stat, q_df, q_p = cochran_q(matrix)
    contrasts = [
        ("Structural − Minimal", "minimal", "structural"),
        ("Relational − Structural", "structural", "relational"),
        ("Full − Relational", "relational", "full"),
    ]
    pairwise = []
    raw_p = []
    for index, (label, lower, higher) in enumerate(contrasts):
        lower_values = [int(by_block[block][lower]["verified_repair_success"]) for block in sorted(by_block)]
        higher_values = [int(by_block[block][higher]["verified_repair_success"]) for block in sorted(by_block)]
        lower_only, higher_only, p_value = exact_mcnemar(lower_values, higher_values)
        rd, lo, hi = bootstrap_paired_rd(lower_values, higher_values, 20260728 + index)
        raw_p.append(p_value)
        pairwise.append(
            {
                "Contrast": label,
                "Lower-only": lower_only,
                "Higher-only": higher_only,
                "Risk difference (pp)": f"{100*rd:+.1f}",
                "95% bootstrap CI (pp)": f"[{100*lo:+.1f}, {100*hi:+.1f}]",
                "Exact McNemar p": f"{p_value:.6g}",
            }
        )
    adjusted = holm_adjust(raw_p)
    for row, value in zip(pairwise, adjusted):
        row["Holm p"] = f"{value:.6g}"

    summaries = []
    figure_rows = []
    token_rows = []
    quality_summary = []
    qa_summary = []
    for level in LEVELS:
        rows = [row for row in attempts if row["context_level"] == level]
        ladder = Counter(row["verified_repair_ladder"] for row in rows)
        verified_count = sum(row["verified_repair_success"] for row in rows)
        preserved_count = sum(row["behavior_preserving_verified"] for row in rows)
        private_passes = sum(row["private_evaluated"] and row["private_passed"] for row in rows)
        private_regressions = sum(
            row["private_evaluated"] and row["private_passed"] is False for row in rows
        )
        private_not_run = sum(
            row["materialized_artifact_id"] is not None and not row["private_evaluated"]
            for row in rows
        )
        verified_lo, verified_hi = wilson(verified_count, len(rows))
        preserved_lo, preserved_hi = wilson(preserved_count, len(rows))
        summaries.append(
            {
                "Context": LEVEL_LABEL[level],
                "n": len(rows),
                "Unapplicable": ladder["unapplicable"],
                "Build failed": ladder["build_fails"],
                "Built unresolved": ladder["builds_unresolved"],
                "Detector-resolved": verified_count,
                "Verified rate [95% CI]": (
                    f"{100*verified_count/len(rows):.1f}% "
                    f"[{100*verified_lo:.1f}, {100*verified_hi:.1f}]"
                ),
                "Layer 3 pass": private_passes,
                "Layer 3 regression": private_regressions,
                "Layer 3 not run": private_not_run,
                "Behavior-preserving verified": preserved_count,
            }
        )
        figure_rows.append(
            {
                "Context": LEVEL_LABEL[level],
                "verified_rate": 100 * verified_count / len(rows),
                "verified_lo": 100 * verified_lo,
                "verified_hi": 100 * verified_hi,
                "preserved_rate": 100 * preserved_count / len(rows),
                "preserved_lo": 100 * preserved_lo,
                "preserved_hi": 100 * preserved_hi,
            }
        )
        token_rows.append(
            {
                "Context": LEVEL_LABEL[level],
                "Mean prompt characters": f"{sum(row['prompt_characters'] for row in rows)/len(rows):.1f}",
                "Generation input tokens": sum(row["generation_input_tokens"] for row in rows),
                "Generation output tokens": sum(row["generation_output_tokens"] for row in rows),
                "Applier input tokens": sum(row["applier_input_tokens"] for row in rows),
                "Applier output tokens": sum(row["applier_output_tokens"] for row in rows),
                "Nominal Sol cost (USD)": f"{sum(row['nominal_sol_cost_usd'] for row in rows):.4f}",
            }
        )
        quality_materialized = [row for row in rows if row["smell_total_delta"] is not None]
        quality_summary.append(
            {
                "Context": LEVEL_LABEL[level],
                "Materialized n": len(quality_materialized),
                "Mean smell delta": (
                    f"{sum(row['smell_total_delta'] for row in quality_materialized)/len(quality_materialized):+.3f}"
                    if quality_materialized
                    else "NA"
                ),
                "Mean CA headline delta": (
                    f"{sum(row['ca_headline_total_delta'] for row in quality_materialized)/len(quality_materialized):+.3f}"
                    if quality_materialized
                    else "NA"
                ),
                "Mean CA all-rules delta": (
                    f"{sum(row['ca_all_total_delta'] for row in quality_materialized)/len(quality_materialized):+.3f}"
                    if quality_materialized
                    else "NA"
                ),
            }
        )
        qa_summary.append(
            {
                "Context": LEVEL_LABEL[level],
                "Outputs": len(rows),
                "Any named quality attribute": (
                    f"{100*sum(bool(row['quality_attributes_mentioned']) for row in rows)/len(rows):.1f}%"
                ),
                "At least one expected": (
                    f"{100*sum(row['at_least_one_expected_attribute'] for row in rows)/len(rows):.1f}%"
                ),
                "All expected": (
                    f"{100*sum(row['all_expected_attributes'] for row in rows)/len(rows):.1f}%"
                ),
            }
        )

    pattern_rows = []
    for pattern in PATTERN_LABEL:
        for level in LEVELS:
            rows = [
                row for row in attempts
                if row["anti_pattern_type"] == pattern and row["context_level"] == level
            ]
            pattern_rows.append(
                {
                    "Anti-pattern": PATTERN_LABEL[pattern],
                    "Context": LEVEL_LABEL[level],
                    "Verified repair": f"{sum(row['verified_repair_success'] for row in rows)}/{len(rows)}",
                    "Behavior-preserving verified": (
                        f"{sum(row['behavior_preserving_verified'] for row in rows)}/{len(rows)}"
                    ),
                }
            )

    inference_rows = [
        {
            "Test": "Global Cochran Q",
            "Statistic": f"{q_stat:.4f}",
            "df": q_df,
            "p": f"{q_p:.6g}",
            "Holm p": "—",
        }
    ] + [
        {
            "Test": row["Contrast"],
            "Statistic": f"{row['Lower-only']} vs {row['Higher-only']} discordant",
            "df": "—",
            "p": row["Exact McNemar p"],
            "Holm p": row["Holm p"],
        }
        for row in pairwise
    ]

    write_table_variants(tables_dir, "table5_9b_four_level_grounding_results", summaries)
    write_table_variants(tables_dir, "table5_9c_grounding_matched_inference", inference_rows)
    write_table_variants(tables_dir, "table5_9d_grounding_tokens_cost", token_rows)
    write_table_variants(tables_dir, "grounding_results_by_antipattern", pattern_rows)
    write_table_variants(tables_dir, "grounding_whole_solution_quality", quality_summary)
    write_table_variants(tables_dir, "grounding_quality_attribute_alignment", qa_summary)
    write_csv(source_dir / "grounding_pairwise_risk_differences.csv", pairwise)
    write_csv(source_dir / "figure5_9_grounding_context_effect.csv", figure_rows)

    statistics = {
        "cochran_q": {"statistic": q_stat, "df": q_df, "p": q_p},
        "pairwise": pairwise,
        "bootstrap_repetitions": 20000,
        "bootstrap_seed_base": 20260728,
        "holm_family": [label for label, _, _ in contrasts],
    }
    (source_dir / "grounding_statistics.json").write_text(
        json.dumps(statistics, indent=2) + "\n", encoding="utf-8"
    )
    summary_json = {
        "campaign_id": manifest["campaign_id"],
        "model": manifest["model_name"],
        "targets": 30,
        "assignments": 120,
        "context_summary": summaries,
        "statistics": statistics,
        "combined_nominal_sol_cost_usd": sum(row["nominal_sol_cost_usd"] for row in attempts),
        "applier_cost_status": "not computed; deployment price was not frozen",
        "private_result_sha256": sha256(experiment / "private-results" / "layer3-campaign.jsonl"),
        "quality_rescore_sha256": sha256(results / "quality-rescore.jsonl"),
    }
    (results / "grounding-analysis-summary.json").write_text(
        json.dumps(summary_json, indent=2) + "\n", encoding="utf-8"
    )
    figure_svg(figure_rows, figures_dir / "figure5_9_grounding_context_effect.svg")

    report = (
        "# Four-level grounding supplement\n\n"
        "This separately frozen 30-target matched experiment compares Minimal, Structural, "
        "Relational, and Full detector context using one GPT-5.6 Sol observation per "
        "target-level cell. It supplements and does not alter the completed 2 × 2 × 2 "
        "confirmatory factorial.\n\n"
        "## Table 5.9b: Four-level grounding effectiveness\n\n"
        + markdown_table(summaries)
        + "\n## Matched inference\n\n"
        + markdown_table(inference_rows)
        + "\n## Adjacent paired risk differences\n\n"
        + markdown_table(pairwise)
        + "\n## Token consumption and nominal Sol cost\n\n"
        + markdown_table(token_rows)
        + "\nOne repetition per target-level cell prevents estimation of within-cell stochastic "
        "variance. Obsolete API private outcomes use a smoke oracle and remain stratified "
        "in the source tables. Full differs from Relational through frozen factual project "
        "metadata; all targets occupy unique files, so no co-located findings were available.\n"
    )
    (package / "GROUNDING_SUPPLEMENT.md").write_text(report, encoding="utf-8")

    public = args.public_output.resolve()
    for subdir in ("tables", "figures", "source-data"):
        (public / subdir).mkdir(parents=True, exist_ok=True)
    for source in tables_dir.glob("table5_9[bcde]_grounding*.*"):
        shutil.copy2(source, public / "tables" / source.name)
    for source in tables_dir.glob("grounding_*.*"):
        shutil.copy2(source, public / "tables" / source.name)
    for source in source_dir.glob("grounding_*"):
        shutil.copy2(source, public / "source-data" / source.name)
    shutil.copy2(source_dir / "figure5_9_grounding_context_effect.csv", public / "source-data")
    shutil.copy2(package / "GROUNDING_SUPPLEMENT.md", public / "GROUNDING_SUPPLEMENT.md")
    print(json.dumps(summary_json, indent=2))


if __name__ == "__main__":
    main()
