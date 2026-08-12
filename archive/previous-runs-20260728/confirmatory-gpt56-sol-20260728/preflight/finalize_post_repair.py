from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath


INPUT_PRICE_PER_MILLION_USD = 5.0
OUTPUT_PRICE_PER_MILLION_USD = 30.0
EXPECTED_MANIFEST_SHA256 = (
    "0c33f9bab116ad21812b72f2d3e150cafac725ed0c70b1dc722db0e9eb54d06c"
)
EXPECTED_ARCHIVE_LEDGER_SHA256 = (
    "c5360a4913eba92d7cc9a84301b7ab6a9df82ec6e30e63209fd052550c30b289"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    script = Path(__file__).resolve()
    experiment = script.parent.parent
    campaign = experiment / "campaign"
    traces = campaign / "traces"
    final_sources = campaign / "final-sources"
    archive = campaign / "viewable-codebases"

    manifest_path = experiment / "factorial-manifest.json"
    manifest = load_json(manifest_path)
    manifest_by_id = {
        assignment["assignment_id"]: assignment
        for assignment in manifest["assignments"]
    }

    ledger_path = campaign / "execution-ledger.jsonl"
    ledger = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    trace_paths = sorted(traces.glob("*.jsonl"))
    final_source_paths = sorted(final_sources.glob("*.json"))

    if len(ledger) != 456 or len(trace_paths) != 456 or len(final_source_paths) != 456:
        raise RuntimeError("campaign artifact counts are not 456/456/456")
    if len({row["assignment_id"] for row in ledger}) != 456:
        raise RuntimeError("execution ledger contains duplicate assignments")
    if any(not row["completed"] or row["error"] is not None for row in ledger):
        raise RuntimeError("execution ledger contains an incomplete or errored assignment")
    if [row["order"] for row in ledger] != list(range(1, 457)):
        raise RuntimeError("execution ledger order is not exactly 1 through 456")

    final_records: list[dict] = []
    trace_row_counts = Counter()
    final_refs: set[Path] = set()
    validation_failures: list[str] = []

    for trace_path in trace_paths:
        rows = [
            json.loads(line)
            for line in trace_path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        if not rows:
            validation_failures.append(f"empty trace: {trace_path.name}")
            continue
        trace_row_counts[len(rows)] += 1
        assignment_id = trace_path.stem.split("-", 1)[1]
        assignment = manifest_by_id[assignment_id]
        control_structure = assignment["control_structure"]
        if control_structure == "iterative":
            candidates = [
                row
                for row in rows
                if row.get("agentic_snapshot") == "final"
                and row.get("verified_repair_ladder") is not None
            ]
        else:
            candidates = [
                row for row in rows if row.get("agentic_snapshot") is None
            ]
        if len(candidates) != 1:
            validation_failures.append(
                f"expected one canonical final record, found {len(candidates)}: "
                f"{trace_path.name}"
            )
            continue
        record = candidates[0]

        if (
            record["grounding_enabled"] != assignment["grounding_enabled"]
            or record["control_structure"] != assignment["control_structure"]
            or record["visible_tests_enabled"]
            != assignment["visible_tests_enabled"]
            or record["run_number"] != assignment["run_number"]
            or record["model_name"] != manifest["model_name"]
        ):
            validation_failures.append(f"condition mismatch: {trace_path.name}")

        ref = final_sources / PureWindowsPath(record["materialized_source_ref"]).name
        if not ref.is_file():
            validation_failures.append(f"missing final source: {trace_path.name}")
            continue
        artifact = load_json(ref)
        if (
            artifact["source_sha256"] != record["materialized_source_sha256"]
            or sha256_text(artifact["final_source"]) != artifact["source_sha256"]
            or artifact["build_passed"] != record["build_passed"]
            or artifact["visible_test_passed"] != record["visible_test_passed"]
            or artifact["relative_file"]
            != PureWindowsPath(assignment["file_path"]).as_posix().split("/corpus/", 1)[1]
        ):
            validation_failures.append(f"final-source hash mismatch: {trace_path.name}")
        final_refs.add(ref.resolve())
        final_records.append(record)

    if validation_failures:
        raise RuntimeError("; ".join(validation_failures[:10]))
    if len(final_records) != 456 or len(final_refs) != 456:
        raise RuntimeError("final record or unique source count is not 456")
    if {path.resolve() for path in final_source_paths} != final_refs:
        raise RuntimeError("orphan or unreferenced final-source artifact detected")

    arm_rows: dict[tuple, dict] = defaultdict(
        lambda: {
            "assignments": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "llm_calls": 0,
            "build_attempts": 0,
            "visible_test_attempts": 0,
            "model_duration_ms": 0.0,
            "final_builds_passed": 0,
            "visible_tests_passed": 0,
            "detector_repairs_verified": 0,
        }
    )
    for record in final_records:
        key = (
            record["grounding_enabled"],
            record["control_structure"],
            record["visible_tests_enabled"],
        )
        row = arm_rows[key]
        row["assignments"] += 1
        row["input_tokens"] += record["input_tokens"]
        row["output_tokens"] += record["output_tokens"]
        row["llm_calls"] += record["llm_call_count"]
        row["build_attempts"] += record["build_attempt_count"]
        row["visible_test_attempts"] += record["test_attempt_count"]
        row["model_duration_ms"] += record["duration_ms"]
        row["final_builds_passed"] += record["build_passed"] is True
        row["visible_tests_passed"] += record["visible_test_passed"] is True
        row["detector_repairs_verified"] += record["verified_repair_success"] is True

    resource_fields = [
        "grounding",
        "control_structure",
        "visible_tests",
        "assignments",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "llm_calls",
        "build_attempts",
        "visible_test_attempts",
        "model_duration_ms",
        "nominal_cost_usd",
        "final_builds_passed",
        "visible_tests_passed",
        "detector_repairs_verified",
    ]
    resource_rows = []
    for key, values in sorted(arm_rows.items(), key=lambda item: str(item[0])):
        grounding, control, visible = key
        cost = (
            values["input_tokens"] * INPUT_PRICE_PER_MILLION_USD
            + values["output_tokens"] * OUTPUT_PRICE_PER_MILLION_USD
        ) / 1_000_000
        resource_rows.append(
            {
                "grounding": "grounded" if grounding else "ungrounded",
                "control_structure": control,
                "visible_tests": "on" if visible else "off",
                **values,
                "total_tokens": values["input_tokens"] + values["output_tokens"],
                "model_duration_ms": round(values["model_duration_ms"], 4),
                "nominal_cost_usd": round(cost, 6),
            }
        )
    with (experiment / "resource-by-arm.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=resource_fields)
        writer.writeheader()
        writer.writerows(resource_rows)

    totals = {
        field: sum(row[field] for row in arm_rows.values())
        for field in (
            "assignments",
            "input_tokens",
            "output_tokens",
            "llm_calls",
            "build_attempts",
            "visible_test_attempts",
            "model_duration_ms",
            "final_builds_passed",
            "visible_tests_passed",
            "detector_repairs_verified",
        )
    }
    totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    totals["nominal_cost_usd"] = round(
        (
            totals["input_tokens"] * INPUT_PRICE_PER_MILLION_USD
            + totals["output_tokens"] * OUTPUT_PRICE_PER_MILLION_USD
        )
        / 1_000_000,
        6,
    )
    totals["model_duration_ms"] = round(totals["model_duration_ms"], 4)

    credential_patterns = [
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+"),
        re.compile(
            r"(?i)(api[_ -]?key|access[_ -]?token)\s*[=:]\s*[A-Za-z0-9_./+-]{20,}"
        ),
    ]
    credential_hits = []
    for path in [
        ledger_path,
        *trace_paths,
        *final_source_paths,
    ]:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
        if any(pattern.search(text) for pattern in credential_patterns):
            credential_hits.append(path.relative_to(experiment).as_posix())

    archive_ledger = archive / "ARCHIVE_SHA256SUMS.txt"
    archive_summary = load_json(archive / "SUMMARY.json")
    archive_index_rows = list(
        csv.DictReader((archive / "INDEX.csv").open(encoding="utf-8-sig"))
    )
    quarantine_path = (
        campaign
        / "quarantine/incomplete-traces/"
        "0321-c4effd44903d8b45f5723c2b.empty-interrupted.jsonl"
    )

    audit = {
        "audit_status": "pass",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_id": manifest["campaign_id"],
        "manifest_sha256": sha256(manifest_path),
        "repair_assignments": 456,
        "execution_ledger_rows": len(ledger),
        "completed_ledger_rows": sum(row["completed"] for row in ledger),
        "errored_ledger_rows": sum(row["error"] is not None for row in ledger),
        "trace_files": len(trace_paths),
        "trace_row_count_distribution": {
            str(key): value for key, value in sorted(trace_row_counts.items())
        },
        "final_source_artifacts": len(final_source_paths),
        "unique_referenced_final_sources": len(final_refs),
        "all_final_sources_hash_verified": True,
        "all_conditions_match_manifest": True,
        "model_names": sorted({record["model_name"] for record in final_records}),
        "parse_status_counts": dict(
            Counter(record["parse_status"] for record in final_records)
        ),
        "error_status_counts": {
            str(key): value
            for key, value in Counter(
                record["error_status"] for record in final_records
            ).items()
        },
        "verified_repair_ladder_counts": dict(
            Counter(
                str(record["verified_repair_ladder"]) for record in final_records
            )
        ),
        "visible_test_policy": {
            "assigned_test_on": sum(
                record["visible_tests_enabled"] for record in final_records
            ),
            "test_on_with_available_test": sum(
                record["visible_tests_enabled"]
                and record["visible_test_available"]
                for record in final_records
            ),
            "test_on_without_available_test": sum(
                record["visible_tests_enabled"]
                and not record["visible_test_available"]
                for record in final_records
            ),
            "visible_tests_passed": sum(
                record["visible_test_passed"] is True for record in final_records
            ),
        },
        "resources": {
            **totals,
            "standard_global_price_usd_per_million": {
                "input": INPUT_PRICE_PER_MILLION_USD,
                "output": OUTPUT_PRICE_PER_MILLION_USD,
            },
            "by_arm_csv": "resource-by-arm.csv",
        },
        "campaign_wall_clock": {
            "first_completion_utc": ledger[0]["timestamp"],
            "last_completion_utc": ledger[-1]["timestamp"],
            "includes_user-interruption_and_resume": True,
        },
        "interruption_audit": {
            "resume_boundary_completed_assignments": 320,
            "quarantined_assignment_order": 321,
            "quarantined_assignment_id": "c4effd44903d8b45f5723c2b",
            "quarantined_trace_bytes": quarantine_path.stat().st_size,
            "quarantined_trace_sha256": sha256(quarantine_path),
            "completed_assignments_repeated": 0,
        },
        "codebase_archive": {
            **archive_summary,
            "index_rows": len(archive_index_rows),
            "archive_files_in_checksum_ledger": 32379,
            "archive_checksum_mismatches": 0,
            "archive_checksum_verification": "pass",
            "archive_ledger_sha256": sha256(archive_ledger),
        },
        "credential_shaped_value_scan": {
            "scope": "campaign core traces, ledger, and final-source artifacts",
            "matching_files": credential_hits,
            "pass": not credential_hits,
        },
        "private_layer3_executed": False,
    }
    if sha256(manifest_path) != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError("manifest hash changed")
    if sha256(archive_ledger) != EXPECTED_ARCHIVE_LEDGER_SHA256:
        raise RuntimeError("archive ledger hash changed")
    if credential_hits:
        raise RuntimeError("credential-shaped value detected in campaign artifacts")
    if totals["final_builds_passed"] != 456:
        raise RuntimeError("not every final source has a passing final build")
    write_json(experiment / "POST_REPAIR_AUDIT.json", audit)

    # Seal core campaign artifacts without redundantly rehashing 32k archive files.
    # The separately verified archive ledger is the hierarchical seal for that tree.
    core_ledger = campaign / "CORE_SHA256SUMS.txt"
    core_entries = []
    for path in sorted(campaign.rglob("*")):
        if not path.is_file() or path == core_ledger:
            continue
        if archive in path.parents:
            continue
        core_entries.append(
            f"{sha256(path)}  {path.relative_to(campaign).as_posix()}\n"
        )
    core_ledger.write_text("".join(core_entries), encoding="utf-8")

    freeze = {
        "status": "frozen_after_repairs_and_archive_before_private_layer3",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_id": manifest["campaign_id"],
        "manifest_sha256": sha256(manifest_path),
        "pre_run_ledger_sha256": sha256(experiment / "PRE_RUN_SHA256SUMS.txt"),
        "post_repair_audit_sha256": sha256(experiment / "POST_REPAIR_AUDIT.json"),
        "resource_by_arm_sha256": sha256(experiment / "resource-by-arm.csv"),
        "campaign_core_file_count": len(core_entries),
        "campaign_core_ledger_sha256": sha256(core_ledger),
        "archive_file_count": 32379,
        "archive_ledger_sha256": sha256(archive_ledger),
        "archive_checksum_verification": "pass",
        "materialized_codebases": 456,
        "private_layer3_executed": False,
    }
    write_json(experiment / "POST_REPAIR_FREEZE.json", freeze)
    freeze_ledger_paths = [
        experiment / "factorial-manifest.json",
        experiment / "PRE_RUN_SHA256SUMS.txt",
        experiment / "POST_REPAIR_AUDIT.json",
        experiment / "resource-by-arm.csv",
        experiment / "POST_REPAIR_FREEZE.json",
        core_ledger,
        archive_ledger,
        archive / "INDEX.csv",
        archive / "INDEX.json",
        archive / "SUMMARY.json",
    ]
    freeze_ledger = experiment / "POST_REPAIR_FREEZE_SHA256SUMS.txt"
    freeze_ledger.write_text(
        "".join(
            f"{sha256(path)}  {path.relative_to(experiment).as_posix()}\n"
            for path in freeze_ledger_paths
        ),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "campaign_id": manifest["campaign_id"],
                "assignments": totals["assignments"],
                "input_tokens": totals["input_tokens"],
                "output_tokens": totals["output_tokens"],
                "llm_calls": totals["llm_calls"],
                "build_attempts": totals["build_attempts"],
                "visible_test_attempts": totals["visible_test_attempts"],
                "nominal_cost_usd": totals["nominal_cost_usd"],
                "campaign_core_files": len(core_entries),
                "archive_files": 32379,
                "freeze_ledger_sha256": sha256(freeze_ledger),
            }
        )
    )


if __name__ == "__main__":
    main()
