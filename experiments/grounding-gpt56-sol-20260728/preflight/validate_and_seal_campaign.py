from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT = Path(__file__).resolve().parents[1]
CAMPAIGN = EXPERIMENT / "campaign"
MANIFEST_PATH = EXPERIMENT / "grounding-manifest.json"
LEDGER_PATH = CAMPAIGN / "execution-ledger.jsonl"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def verify_checksum_file(path: Path, skipped: set[str] | None = None) -> int:
    skipped = skipped or set()
    verified = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        if relative in skipped:
            continue
        target = path.parent / relative
        if not target.exists():
            target = ROOT / relative
        if not target.exists():
            raise FileNotFoundError(f"checksum target missing: {relative}")
        actual = sha256(target)
        if actual != expected:
            raise ValueError(
                f"checksum mismatch for {relative}: expected {expected}, got {actual}"
            )
        verified += 1
    return verified


def main() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assignments = manifest["assignments"]
    assignment_by_id = {row["assignment_id"]: row for row in assignments}
    ledger = read_jsonl(LEDGER_PATH)

    if len(assignments) != 120 or len(assignment_by_id) != 120:
        raise ValueError("manifest must contain exactly 120 unique assignments")
    if len(ledger) != 120:
        raise ValueError(f"execution ledger has {len(ledger)} rows, expected 120")
    if len({row["assignment_id"] for row in ledger}) != 120:
        raise ValueError("execution ledger contains duplicate assignment IDs")
    if sorted(row["order"] for row in ledger) != list(range(1, 121)):
        raise ValueError("execution ledger orders are not exactly 1..120")
    if any(not row.get("completed") or row.get("error") for row in ledger):
        raise ValueError("execution ledger contains incomplete or errored rows")
    if any(row["campaign_id"] != manifest["campaign_id"] for row in ledger):
        raise ValueError("campaign ID mismatch in execution ledger")

    context_counts = Counter(row["context_level"] for row in ledger)
    expected_context_counts = {
        "minimal": 30,
        "structural": 30,
        "relational": 30,
        "full": 30,
    }
    if dict(context_counts) != expected_context_counts:
        raise ValueError(f"unbalanced context levels: {dict(context_counts)}")

    pattern_counts = Counter(
        assignment_by_id[row["assignment_id"]]["anti_pattern_type"] for row in ledger
    )
    expected_pattern_counts = {
        "god_class": 40,
        "long_method": 40,
        "obsolete_api_usage": 40,
    }
    if dict(pattern_counts) != expected_pattern_counts:
        raise ValueError(f"unbalanced anti-patterns: {dict(pattern_counts)}")

    trace_paths = sorted((CAMPAIGN / "traces").glob("*.jsonl"))
    if len(trace_paths) != 120:
        raise ValueError(f"found {len(trace_paths)} trace files, expected 120")

    ladder_counts: Counter[str] = Counter()
    model_counts: Counter[str] = Counter()
    applier_counts: Counter[str] = Counter()
    trace_record_counts: Counter[int] = Counter()
    materialized_refs: set[Path] = set()
    total_evaluated_calls = 0
    total_applier_calls = 0
    total_input_tokens = 0
    total_output_tokens = 0

    for execution in sorted(ledger, key=lambda row: row["order"]):
        assignment = assignment_by_id.get(execution["assignment_id"])
        if assignment is None:
            raise ValueError(f"unknown assignment {execution['assignment_id']}")
        if execution["order"] != assignment["order"]:
            raise ValueError(f"order mismatch for {execution['assignment_id']}")
        if execution["context_level"] != assignment["context_level"]:
            raise ValueError(f"context mismatch for {execution['assignment_id']}")
        if execution["evaluated_model_calls"] != 1:
            raise ValueError(f"evaluated-model call count is not one: {execution}")
        if execution["applier_calls"] not in (0, 1):
            raise ValueError(f"invalid applier call count: {execution}")

        trace_path = local_path(execution["trace_file"])
        if not trace_path.exists():
            raise FileNotFoundError(trace_path)
        if sha256(trace_path) != execution["trace_sha256"]:
            raise ValueError(f"trace hash mismatch: {trace_path}")
        records = read_jsonl(trace_path)
        expected_records = 1 + execution["applier_calls"]
        if len(records) != expected_records:
            raise ValueError(
                f"{trace_path} has {len(records)} records, expected {expected_records}"
            )
        if [record["run_id"] for record in records] != execution["run_ids"]:
            raise ValueError(f"run ID mismatch: {trace_path}")

        generation = records[0]
        if generation["model_name"] != manifest["model_name"]:
            raise ValueError(f"wrong evaluated model: {trace_path}")
        if generation["prompt_version"] != manifest["prompt_version"]:
            raise ValueError(f"wrong prompt version: {trace_path}")
        if generation["context_level"] != assignment["context_level"]:
            raise ValueError(f"trace context mismatch: {trace_path}")
        if generation["anti_pattern_type"] != assignment["anti_pattern_type"]:
            raise ValueError(f"trace anti-pattern mismatch: {trace_path}")
        if generation["symbol_name"] != assignment["symbol_name"]:
            raise ValueError(f"trace symbol mismatch: {trace_path}")
        model_counts[generation["model_name"]] += 1

        if execution["applier_calls"] == 1:
            verification = records[1]
            if verification["source_run_id"] != generation["run_id"]:
                raise ValueError(f"applier source run mismatch: {trace_path}")
            if verification["applier_model"] != manifest["applier_model"]:
                raise ValueError(f"wrong applier model: {trace_path}")
            if verification["applier_prompt_version"] != manifest["applier_prompt_version"]:
                raise ValueError(f"wrong applier prompt version: {trace_path}")
            ladder = verification["verified_repair_ladder"]
            ladder_counts[ladder] += 1
            applier_counts[verification["applier_model"]] += 1

            ref = verification.get("materialized_source_ref")
            if ref:
                artifact_path = local_path(ref)
                if not artifact_path.exists():
                    raise FileNotFoundError(artifact_path)
                artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
                if sha256_text(artifact["final_source"]) != artifact["source_sha256"]:
                    raise ValueError(f"source hash mismatch in {artifact_path}")
                if verification["materialized_source_sha256"] != artifact["source_sha256"]:
                    raise ValueError(f"trace/artifact source hash mismatch: {artifact_path}")
                materialized_refs.add(artifact_path.resolve())
        else:
            ladder_counts["no_applier_call"] += 1

        record_input_tokens = sum(int(record.get("input_tokens") or 0) for record in records)
        record_output_tokens = sum(int(record.get("output_tokens") or 0) for record in records)
        if record_input_tokens != execution["input_tokens"]:
            raise ValueError(f"input token mismatch: {trace_path}")
        if record_output_tokens != execution["output_tokens"]:
            raise ValueError(f"output token mismatch: {trace_path}")

        trace_record_counts[len(records)] += 1
        total_evaluated_calls += execution["evaluated_model_calls"]
        total_applier_calls += execution["applier_calls"]
        total_input_tokens += execution["input_tokens"]
        total_output_tokens += execution["output_tokens"]

    actual_final_sources = {
        path.resolve() for path in (CAMPAIGN / "final-sources").glob("*.json")
    }
    if actual_final_sources != materialized_refs:
        missing = sorted(str(path) for path in materialized_refs - actual_final_sources)
        extra = sorted(str(path) for path in actual_final_sources - materialized_refs)
        raise ValueError(f"final-source set mismatch; missing={missing}, extra={extra}")

    frozen_checks = {
        "pre_run": verify_checksum_file(EXPERIMENT / "PRE_RUN_SHA256SUMS.txt"),
        "amendment_1": verify_checksum_file(
            EXPERIMENT / "PRE_RUN_AMENDMENT_1_SHA256SUMS.txt",
            {
                # These amendment-1 states were explicitly superseded and re-frozen
                # by amendment 2. The immutable amendment-1 record itself is checked.
                "experiments/grounding-gpt56-sol-20260728/DEVIATIONS.md",
                "src/HybridLens.CLI/Commands/GroundingCampaignCommand.cs",
                "src/HybridLens.CLI/bin/Debug/net10.0/HybridLens.CLI.dll",
            },
        ),
        "amendment_2": verify_checksum_file(
            EXPERIMENT / "PRE_RUN_AMENDMENT_2_SHA256SUMS.txt",
            {"experiments/grounding-gpt56-sol-20260728/campaign/execution-ledger.jsonl"},
        ),
    }

    checksum_targets = [
        EXPERIMENT / "PROTOCOL.md",
        EXPERIMENT / "grounding-baseline.jsonl",
        MANIFEST_PATH,
        EXPERIMENT / "PRE_RUN_AUDIT.json",
        EXPERIMENT / "PRE_RUN_SHA256SUMS.txt",
        EXPERIMENT / "PRE_RUN_AMENDMENT_1.json",
        EXPERIMENT / "PRE_RUN_AMENDMENT_1_SHA256SUMS.txt",
        EXPERIMENT / "PRE_RUN_AMENDMENT_2.json",
        EXPERIMENT / "PRE_RUN_AMENDMENT_2_SHA256SUMS.txt",
        EXPERIMENT / "DEVIATIONS.md",
        LEDGER_PATH,
        *trace_paths,
        *sorted(actual_final_sources),
    ]
    checksum_lines = [
        f"{sha256(path)}  {path.relative_to(ROOT).as_posix()}" for path in checksum_targets
    ]
    checksum_path = EXPERIMENT / "POST_REPAIR_SHA256SUMS.txt"
    checksum_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n")

    audit = {
        "status": "repair_campaign_sealed",
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_id": manifest["campaign_id"],
        "manifest_sha256": sha256(MANIFEST_PATH),
        "execution_ledger_sha256": sha256(LEDGER_PATH),
        "post_repair_checksum_ledger_sha256": sha256(checksum_path),
        "assignments": len(ledger),
        "unique_targets": len({row["block_id"] for row in assignments}),
        "context_counts": expected_context_counts,
        "anti_pattern_assignment_counts": expected_pattern_counts,
        "trace_files": len(trace_paths),
        "trace_record_counts": dict(sorted(trace_record_counts.items())),
        "evaluated_model_calls": total_evaluated_calls,
        "applier_calls": total_applier_calls,
        "evaluated_model_counts": dict(model_counts),
        "applier_model_counts": dict(applier_counts),
        "materialized_final_sources": len(actual_final_sources),
        "non_materialized_assignments": len(ledger) - len(actual_final_sources),
        "verified_repair_ladder": dict(sorted(ladder_counts.items())),
        "combined_input_tokens": total_input_tokens,
        "combined_output_tokens": total_output_tokens,
        "frozen_checksum_entries_verified": frozen_checks,
        "private_layer3_executed": False,
    }
    audit_path = EXPERIMENT / "POST_REPAIR_AUDIT.json"
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8", newline="\n")

    seal_path = EXPERIMENT / "POST_REPAIR_SEAL_SHA256SUMS.txt"
    seal_path.write_text(
        f"{sha256(checksum_path)}  {checksum_path.relative_to(ROOT).as_posix()}\n"
        f"{sha256(audit_path)}  {audit_path.relative_to(ROOT).as_posix()}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
