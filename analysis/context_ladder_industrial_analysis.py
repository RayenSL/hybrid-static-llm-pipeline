#!/usr/bin/env python3
"""Analyze the sealed four-level direct-edit context-ladder campaign on Ibis.Besteksadministratie.

Descriptive only. Nine targets, no control condition: report ordinal ladder outcomes, the
three-valued external oracle, whole-solution quality deltas, truncation, and tokens/cost, all by
level and by target. No hypothesis test is computed here, and none should be added: the runbook
for this experiment (RUNBOOK-context-ladder-industrial.md) is explicit that discordant pairs bind
the inferential floor above conventional thresholds regardless of what the data show.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

try:
    from analysis.context_ladder_analysis import validate_model_ready_data
except ModuleNotFoundError:  # Direct execution: python analysis/context_ladder_industrial_analysis.py
    from context_ladder_analysis import validate_model_ready_data

LEVELS = ["minimal", "structural", "relational", "full"]
COST_BASIS = "frozen nominal USD: $5/M input and $30/M output tokens"

# One entry per admitted target file, keyed by file name (unique across the 9 targets).
TARGET_MAP = {
    "Extensions.cs": "BES-LM-01",
    "ProjectManager.cs": "BES-LM-02",
    "ReportFinalStatement.cs": "BES-LM-03",
    "ReportPeriodState.cs": "BES-LM-04",
    "ImageMetadataService.cs": "BES-LM-05",
    "ReportResolverFactory.cs": "BES-LM-06",
    "AttachmentService.cs": "BES-LM-07",
    "ProjectManagerProject.cs": "BES-LM-08",
    "ReportHelpers.cs": "BES-GC-01",
}
GOD_CLASS_TARGETS = {"BES-GC-01"}
READER_REJECTED_TARGETS = {"BES-LM-06"}
READER_REJECTED_NOTE = (
    "reader-rejected control (is_long_method: no); its oracle cannot distinguish the eighteen "
    "switch arms CreateInstance<T> dispatches through, since ServiceActivator.GetScope() is a "
    "static locator with no container in the harness"
)


def target_id_for(file_path: str) -> str:
    name = file_path.replace("\\", "/").rsplit("/", 1)[-1]
    return TARGET_MAP[name]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]


def metric_delta(row: dict | None, before: str, after: str):
    if row is None or row.get(before) is None or row.get(after) is None:
        return None
    return row[after] - row[before]


def mean(rows: list[dict], key: str):
    values = [r[key] for r in rows if r[key] is not None]
    return sum(values) / len(values) if values else None


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def dataframe_markdown(rows: list[dict]) -> str:
    keys = list(rows[0])
    lines = ["| " + " | ".join(keys) + " |", "|" + "|".join("---" for _ in keys) + "|"]
    lines += ["| " + " | ".join(str(r[k]) for k in keys) + " |" for r in rows]
    return "\n".join(lines)


def level_row(level: str, rows: list[dict]) -> dict:
    ladder = Counter(r["verified_repair_ladder"] for r in rows)
    oracle = Counter(r["oracle_outcome"] for r in rows)
    quality = Counter(r["quality_outcome"] for r in rows)
    scored = [r for r in rows if r["smell_delta"] is not None]
    return {
        "level": level, "n": len(rows),
        "resolved": ladder.get("resolved", 0),
        "build_fails": ladder.get("build_fails", 0),
        "builds_unresolved": ladder.get("builds_unresolved", 0),
        "oracle_behaviour_preserved": oracle.get("behaviour_preserved", 0),
        "oracle_behavioural_change": oracle.get("behavioural_change", 0),
        "oracle_public_contract_change": oracle.get("public_contract_change", 0),
        "oracle_production_build_failed": oracle.get("production_build_failed", 0)
                                           + oracle.get("production_build_not_recorded", 0),
        "quality_scored": quality.get("scored", 0),
        "quality_production_build_failed": quality.get("production_build_failed", 0),
        "smell_delta_mean": mean(scored, "smell_delta"),
        "ca_headline_delta_mean": mean(scored, "ca_headline_delta"),
        "ca_all_delta_mean": mean(scored, "ca_all_delta"),
        "cross_file_present_n": sum(r["cross_file_declarations_n"] > 0 for r in rows),
        "cross_file_truncated_n": sum(r["cross_file_truncated"] for r in rows),
        "truncation_rate_pct": 100 * sum(r["cross_file_truncated"] for r in rows) / len(rows),
        "input_tokens_sum": sum(r["input_tokens"] for r in rows),
        "output_tokens_sum": sum(r["output_tokens"] for r in rows),
        "nominal_cost_usd_sum": sum(r["cost_usd"] for r in rows),
        "prompt_characters_mean": mean(rows, "prompt_characters"),
    }


def target_level_row(target_id: str, level: str, rows: list[dict]) -> dict:
    ladder = Counter(r["verified_repair_ladder"] for r in rows)
    oracle = Counter(r["oracle_outcome"] for r in rows)
    scored = [r for r in rows if r["smell_delta"] is not None]
    return {
        "target_id": target_id, "level": level, "n": len(rows),
        "resolved": ladder.get("resolved", 0), "build_fails": ladder.get("build_fails", 0),
        "builds_unresolved": ladder.get("builds_unresolved", 0),
        "oracle_behaviour_preserved": oracle.get("behaviour_preserved", 0),
        "oracle_behavioural_change": oracle.get("behavioural_change", 0),
        "oracle_public_contract_change": oracle.get("public_contract_change", 0),
        "oracle_production_build_failed": oracle.get("production_build_failed", 0)
                                           + oracle.get("production_build_not_recorded", 0),
        "cross_file_declarations_n": sum(r["cross_file_declarations_n"] for r in rows),
        "cross_file_truncated_n": sum(r["cross_file_truncated"] for r in rows),
        "smell_delta_mean": mean(scored, "smell_delta"),
    }


def target_row(target_id: str, rows: list[dict]) -> dict:
    ladder = Counter(r["verified_repair_ladder"] for r in rows)
    oracle = Counter(r["oracle_outcome"] for r in rows)
    full_rows = [r for r in rows if r["context_level"] == "full"]
    full_cross_file = sum(r["cross_file_declarations_n"] for r in full_rows)
    return {
        "target_id": target_id, "symbol_name": rows[0]["symbol_name"],
        "anti_pattern_type": rows[0]["anti_pattern_type"], "n": len(rows),
        "resolved": ladder.get("resolved", 0), "build_fails": ladder.get("build_fails", 0),
        "builds_unresolved": ladder.get("builds_unresolved", 0),
        "oracle_behaviour_preserved": oracle.get("behaviour_preserved", 0),
        "oracle_behavioural_change": oracle.get("behavioural_change", 0),
        "oracle_public_contract_change": oracle.get("public_contract_change", 0),
        "oracle_production_build_failed": oracle.get("production_build_failed", 0)
                                           + oracle.get("production_build_not_recorded", 0),
        "is_god_class_n_of_1": target_id in GOD_CLASS_TARGETS,
        "is_reader_rejected": target_id in READER_REJECTED_TARGETS,
        "full_has_no_cross_file_payload": full_cross_file == 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    exp = args.experiment
    out = args.out
    out.mkdir(parents=True, exist_ok=False)

    manifest = json.loads((exp / "ladder-manifest.json").read_text(encoding="utf-8-sig"))
    ledger = {x["assignment_id"]: x for x in read_jsonl(exp / "campaign/execution-ledger.jsonl")}
    oracle = {x["artifact_id"]: x for x in read_jsonl(exp / "private-results/external-oracle.jsonl")}
    quality = {x["artifact_id"]: x for x in read_jsonl(exp / "private-results/external-quality.jsonl")}

    attempts = []
    for assignment in manifest["assignments"]:
        aid = assignment["assignment_id"]
        entry = ledger[aid]
        trace = read_jsonl(Path(entry["trace_file"]))[-1]
        materialized = json.loads(
            Path(trace["materialized_source_ref"]).read_text(encoding="utf-8-sig"))
        artifact_id = materialized["artifact_id"]
        o = oracle.get(artifact_id)
        q = quality.get(artifact_id)
        target_id = target_id_for(assignment["file_path"])
        input_tokens = int(entry["input_tokens"] or 0)
        output_tokens = int(entry["output_tokens"] or 0)
        attempts.append({
            "assignment_id": aid, "instance_id": target_id, "target_id": target_id,
            "symbol_name": assignment["symbol_name"],
            "anti_pattern_type": assignment["anti_pattern_type"],
            "context_level": assignment["context_level"], "run_number": assignment["run_number"],
            "cross_file_declarations_n": len(assignment.get("cross_file_declarations") or []),
            "cross_file_truncated": bool(assignment.get("cross_file_truncated")),
            "verified_repair_ladder": trace["verified_repair_ladder"],
            "verified_repair_success": bool(trace["verified_repair_success"]),
            "build_passed": trace["build_passed"],
            "context_truncated": bool(trace.get("context_truncated")),
            "artifact_id": artifact_id,
            "oracle_outcome": o["outcome"] if o else None,
            "oracle_passed": o.get("passed") if o else None,
            "quality_outcome": q["outcome"] if q else None,
            "smell_delta": metric_delta(q, "smell_total_before", "smell_total_after"),
            "ca_headline_delta": metric_delta(q, "ca_headline_before", "ca_headline_after"),
            "ca_all_delta": metric_delta(q, "ca_all_before", "ca_all_after"),
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cost_usd": (5 * input_tokens + 30 * output_tokens) / 1e6,
            "prompt_characters": len(trace["raw_user_prompt"]),
            "duration_ms": trace.get("duration_ms"),
        })

    import pandas as pd
    data = pd.DataFrame(attempts)
    observations, instances = validate_model_ready_data(data)
    write_csv(out / "attempts.csv", attempts)

    levels = [level_row(level, [a for a in attempts if a["context_level"] == level]) for level in LEVELS]
    write_csv(out / "level_summary.csv", levels)

    by_target = defaultdict(list)
    for a in attempts:
        by_target[a["target_id"]].append(a)
    target_level = []
    for target_id in sorted(by_target):
        for level in LEVELS:
            rows = [a for a in by_target[target_id] if a["context_level"] == level]
            target_level.append(target_level_row(target_id, level, rows))
    write_csv(out / "target_level_summary.csv", target_level)

    targets = [target_row(target_id, rows) for target_id, rows in sorted(by_target.items())]
    write_csv(out / "target_summary.csv", targets)

    no_full_payload = sorted(t["target_id"] for t in targets if t["full_has_no_cross_file_payload"])
    oracle_overall = Counter(a["oracle_outcome"] for a in attempts)
    quality_overall = Counter(a["quality_outcome"] for a in attempts)

    summary = {
        "observations": observations, "instances": instances,
        "levels": levels, "targets": targets, "target_by_level": target_level,
        "oracle_outcomes_overall": dict(oracle_overall),
        "quality_outcomes_overall": dict(quality_overall),
        "cost_basis": COST_BASIS,
        "notes": {
            "BES-GC-01": "one God Class case (n = 1), never a God Class stratum",
            "BES-LM-06": READER_REJECTED_NOTE,
            "full_equals_relational_targets": no_full_payload,
        },
        "caveats": [
            "Descriptive only: nine targets, no hypothesis test. Discordant pairs bind the "
            "inferential floor above conventional thresholds regardless of the data.",
            "BES-GC-01 is one case, not a God Class result.",
            "No detection recall or precision on this codebase: there is no exhaustive truth set.",
            "Do not pool these denominators with the corpus ladder, the confirmatory factorial, "
            "the sealed supplement, or the feasibility probe.",
            "Detector-resolved does not mean behaviour-preserving.",
            "Oracles are author-written; the self-authored-oracle threat applies here as on the corpus.",
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    report = [
        "# Context-ladder industrial run (Ibis.Besteksadministratie) outcomes", "",
        f"{observations} attempts across {instances} independent targets "
        f"(4 levels x 3 repetitions = 12 attempts per target). Descriptive only: no p-value is "
        f"reported or should be inferred from this data.", "",
        "## Ordinal ladder and external oracle, by level", "",
        dataframe_markdown(levels), "",
        "## Per-target detail (the result, with nine targets)", "",
        dataframe_markdown(targets), "",
        "## Per-target, by level", "",
        dataframe_markdown(target_level), "",
        "## Notes",
        "",
        f"- BES-GC-01: {summary['notes']['BES-GC-01']}.",
        f"- BES-LM-06: {summary['notes']['BES-LM-06']}.",
        f"- Full ≡ Relational structurally (no cross-file payload even at Full): "
        f"{', '.join(no_full_payload)}.",
        "- Detector-resolved does not mean behaviour-preserving; the external oracle and "
        "whole-solution quality scan are the independent behavioural and quality measurements.",
        "- Do not pool these denominators with the corpus ladder, the confirmatory factorial, "
        "the sealed supplement, or the feasibility probe.",
        "",
    ]
    (out / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
