from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


EXPERIMENT = Path(__file__).resolve().parents[1]
CAMPAIGN = EXPERIMENT / "campaign"
PRIVATE_RESULTS = EXPERIMENT / "private-results" / "layer3-campaign.jsonl"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def main() -> None:
    rows = read_jsonl(PRIVATE_RESULTS)
    artifacts = {}
    for path in sorted((CAMPAIGN / "final-sources").glob("*.json")):
        artifact = json.loads(path.read_text(encoding="utf-8"))
        artifact_id = artifact["artifact_id"]
        if artifact_id in artifacts:
            raise ValueError(f"duplicate artifact ID: {artifact_id}")
        artifacts[artifact_id] = (path, artifact)

    if len(rows) != len(artifacts) or len(rows) != 41:
        raise ValueError(
            f"private rows/artifacts mismatch: rows={len(rows)}, artifacts={len(artifacts)}"
        )
    if len({row["evaluation_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate private evaluation IDs")
    if len({row["artifact_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate private artifact IDs")
    if {row["artifact_id"] for row in rows} != set(artifacts):
        raise ValueError("private artifact ID set differs from sealed materialized artifacts")

    for row in rows:
        path, artifact = artifacts[row["artifact_id"]]
        if row["source_sha256"] != artifact["source_sha256"]:
            raise ValueError(f"source hash mismatch for {path}")
        artifact_ref_name = row["artifact_ref"].replace("\\", "/").rsplit("/", 1)[-1]
        if artifact_ref_name != path.name:
            raise ValueError(f"artifact reference mismatch for {path}")

    evaluated_passed = sum(row["evaluated"] and row["passed"] for row in rows)
    evaluated_failed = sum(row["evaluated"] and not row["passed"] for row in rows)
    not_run = sum(not row["evaluated"] for row in rows)
    not_run_reasons = Counter(
        row["not_run_reason"] for row in rows if not row["evaluated"]
    )
    if evaluated_passed + evaluated_failed + not_run != 41:
        raise ValueError("private outcome counts do not sum to 41")

    deviation = (
        "# Post-repair execution note\n\n"
        "The first post-seal `private-layer3` invocation continued in a yielded process "
        "session and completed all 41 materialized artifacts, writing the protected "
        "`private-results/layer3-campaign.jsonl` file. Because only its first four "
        "progress lines were initially surfaced, a diagnostic invocation repeated the "
        "deterministic local build/oracle checks. The command's create-new guard rejected "
        "the diagnostic write because the first result already existed. No model or "
        "applier call occurred, no repair or private result was overwritten, and only "
        "the first 41-row file is used for analysis.\n"
    )
    deviation_path = EXPERIMENT / "POST_REPAIR_EXECUTION_NOTE.md"
    deviation_path.write_text(deviation, encoding="utf-8", newline="\n")

    audit = {
        "status": "private_layer3_sealed",
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "private_result_sha256": sha256(PRIVATE_RESULTS),
        "private_rows": len(rows),
        "materialized_artifacts": len(artifacts),
        "evaluated_passed": evaluated_passed,
        "evaluated_regression": evaluated_failed,
        "not_run": not_run,
        "not_run_reasons": dict(sorted(not_run_reasons.items())),
        "artifact_id_set_match": True,
        "source_hash_match": True,
        "result_used": "first protected 41-row result only",
        "duplicate_diagnostic_execution_used": False,
    }
    audit_path = EXPERIMENT / "POST_PRIVATE_AUDIT.json"
    audit_path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8", newline="\n")

    checksum_path = EXPERIMENT / "POST_PRIVATE_SHA256SUMS.txt"
    targets = [
        EXPERIMENT / "POST_REPAIR_AUDIT.json",
        EXPERIMENT / "POST_REPAIR_SHA256SUMS.txt",
        EXPERIMENT / "POST_REPAIR_SEAL_SHA256SUMS.txt",
        PRIVATE_RESULTS,
        deviation_path,
        audit_path,
    ]
    checksum_path.write_text(
        "".join(f"{sha256(path)}  {path.relative_to(EXPERIMENT).as_posix()}\n" for path in targets),
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
