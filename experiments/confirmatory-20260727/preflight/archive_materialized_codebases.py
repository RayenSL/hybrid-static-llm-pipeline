from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import shutil
from pathlib import Path

SKIP_PARTS = {"bin", "obj", ".git", ".idea", ".vs"}


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_text(value: str) -> str:
    return sha_bytes(value.encode("utf-8"))


def copy_source_tree(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob("*"), key=lambda p: p.relative_to(source).as_posix()):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def unique_materialized_ref(trace_path: Path) -> str | None:
    refs = set()
    for raw in trace_path.read_text(encoding="utf-8-sig").splitlines():
        if not raw.strip():
            continue
        record = json.loads(raw)
        value = record.get("materialized_source_ref")
        if value:
            refs.add(str(Path(value).resolve()))
    if len(refs) > 1:
        raise ValueError(f"trace has multiple materialized source refs: {trace_path}")
    return next(iter(refs), None)


def tree_checksum(directory: Path) -> str:
    lines = []
    for path in sorted(directory.rglob("*"), key=lambda p: p.relative_to(directory).as_posix()):
        if not path.is_file() or path.name == "SHA256SUMS.txt":
            continue
        lines.append(f"{sha_bytes(path.read_bytes())}  {path.relative_to(directory).as_posix()}")
    content = "\n".join(lines) + "\n"
    (directory / "SHA256SUMS.txt").write_text(content, encoding="utf-8", newline="\n")
    return sha_text(content)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--campaign", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    assignments = {row["assignment_id"]: row for row in manifest["assignments"]}
    ledger_path = args.campaign / "execution-ledger.jsonl"
    ledger = [json.loads(raw) for raw in ledger_path.read_text(encoding="utf-8-sig").splitlines() if raw.strip()]
    completed = [row for row in ledger if row.get("completed")]
    if len({row["assignment_id"] for row in completed}) != len(completed):
        raise ValueError("execution ledger contains duplicate completed assignments")
    if args.out.exists() and any(args.out.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty archive directory: {args.out}")
    args.out.mkdir(parents=True, exist_ok=True)

    index = []
    for execution in sorted(completed, key=lambda row: row["order"]):
        assignment = assignments[execution["assignment_id"]]
        trace = Path(execution["trace_file"])
        ref = unique_materialized_ref(trace)
        base = {
            "order": assignment["order"],
            "assignment_id": assignment["assignment_id"],
            "block_id": assignment["block_id"],
            "run_number": assignment["run_number"],
            "anti_pattern_type": assignment["anti_pattern_type"],
            "symbol_name": assignment["symbol_name"],
            "grounding_enabled": assignment["grounding_enabled"],
            "control_structure": assignment["control_structure"],
            "visible_tests_enabled": assignment["visible_tests_enabled"],
            "visible_test_available": assignment.get("visible_test_artifact_ref") is not None,
            "trace_file": str(trace.resolve()),
            "materialized": ref is not None,
        }
        if ref is None:
            index.append(base | {"archive_path": None, "materialized_source_ref": None, "final_source_sha256": None, "archive_tree_sha256": None})
            continue

        artifact_path = Path(ref)
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        final_source = artifact["final_source"]
        if sha_text(final_source) != artifact["source_sha256"]:
            raise ValueError(f"materialized source hash mismatch: {artifact_path}")
        relative_file = Path(artifact["relative_file"])
        pristine_file = args.corpus / relative_file
        if not pristine_file.exists():
            raise FileNotFoundError(pristine_file)
        if sha_text(pristine_file.read_text(encoding="utf-8-sig")) != assignment["pristine_source_sha256"]:
            raise ValueError(f"pristine source drift: {pristine_file}")

        archive = args.out / f"{assignment['order']:04d}-{assignment['assignment_id']}"
        corpus_copy = archive / "corpus"
        copy_source_tree(args.corpus, corpus_copy)
        repaired_file = corpus_copy / relative_file
        repaired_file.parent.mkdir(parents=True, exist_ok=True)
        repaired_file.write_text(final_source, encoding="utf-8", newline="")
        if sha_text(repaired_file.read_text(encoding="utf-8")) != artifact["source_sha256"]:
            raise ValueError(f"archived repaired source hash mismatch: {repaired_file}")

        diff = "".join(difflib.unified_diff(
            pristine_file.read_text(encoding="utf-8-sig").splitlines(keepends=True),
            final_source.splitlines(keepends=True),
            fromfile=f"pristine/{artifact['relative_file']}",
            tofile=f"repaired/{artifact['relative_file']}",
        ))
        metadata = base | {
            "campaign_id": manifest["campaign_id"],
            "relative_file": artifact["relative_file"],
            "materialized_source_ref": str(artifact_path.resolve()),
            "materialized_artifact_id": artifact["artifact_id"],
            "final_source_sha256": artifact["source_sha256"],
            "pristine_source_sha256": assignment["pristine_source_sha256"],
            "prompt_version": assignment["prompt_version"],
            "visible_test_sha256": assignment.get("visible_test_sha256"),
        }
        (archive / "ASSIGNMENT.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline="\n")
        (archive / "REPAIR.diff").write_text(diff, encoding="utf-8", newline="")
        (archive / "README.txt").write_text(
            "This directory is a source-only, directly viewable reconstruction of the complete corpus\n"
            "for one frozen repair assignment. Open corpus/Corpus.sln to inspect or build it.\n"
            "ASSIGNMENT.json records the experimental condition; REPAIR.diff shows the production change.\n",
            encoding="utf-8", newline="\n")
        tree_hash = tree_checksum(archive)
        index.append(base | {
            "archive_path": str(archive.resolve()),
            "materialized_source_ref": str(artifact_path.resolve()),
            "final_source_sha256": artifact["source_sha256"],
            "archive_tree_sha256": tree_hash,
        })

    fields = list(index[0].keys())
    with (args.out / "INDEX.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(index)
    (args.out / "INDEX.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8", newline="\n")
    summary = {
        "campaign_id": manifest["campaign_id"],
        "completed_assignments": len(completed),
        "materialized_codebases": sum(row["materialized"] for row in index),
        "non_materialized_assignments": sum(not row["materialized"] for row in index),
        "archive_contract": "complete source-only corpus + repaired source + metadata + unified diff + checksums",
    }
    (args.out / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    outer = []
    for path in sorted(args.out.rglob("*"), key=lambda p: p.relative_to(args.out).as_posix()):
        if path.is_file() and path.name != "ARCHIVE_SHA256SUMS.txt":
            outer.append(f"{sha_bytes(path.read_bytes())}  {path.relative_to(args.out).as_posix()}")
    (args.out / "ARCHIVE_SHA256SUMS.txt").write_text("\n".join(outer) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, sort_keys=True))

if __name__ == "__main__":
    main()
