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


def local_path(raw: str) -> Path:
    normalized = raw.replace("\\", "/")
    if len(normalized) >= 3 and normalized[1:3] == ":/":
        return Path("/mnt") / normalized[0].lower() / normalized[3:]
    return Path(normalized)


def copy_source_tree(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if any(part in SKIP_PARTS for part in relative.parts):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def materialized_ref(trace_path: Path) -> Path | None:
    refs = {
        local_path(record["materialized_source_ref"]).resolve()
        for line in trace_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
        for record in [json.loads(line)]
        if record.get("materialized_source_ref")
    }
    if len(refs) > 1:
        raise ValueError(f"trace has multiple materialized source refs: {trace_path}")
    return next(iter(refs), None)


def write_tree_checksums(directory: Path) -> str:
    lines = []
    for path in sorted(directory.rglob("*"), key=lambda item: item.relative_to(directory).as_posix()):
        if path.is_file() and path.name != "SHA256SUMS.txt":
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
    ledger = [
        json.loads(line)
        for line in (args.campaign / "execution-ledger.jsonl")
        .read_text(encoding="utf-8-sig")
        .splitlines()
        if line.strip()
    ]
    if len(ledger) != 120 or len({row["assignment_id"] for row in ledger}) != 120:
        raise ValueError("campaign ledger must contain 120 unique assignments")
    if args.out.exists() and any(args.out.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty archive directory: {args.out}")
    args.out.mkdir(parents=True, exist_ok=True)

    index = []
    for execution in sorted(ledger, key=lambda row: row["order"]):
        assignment = assignments[execution["assignment_id"]]
        trace = local_path(execution["trace_file"])
        ref = materialized_ref(trace)
        base = {
            "order": assignment["order"],
            "assignment_id": assignment["assignment_id"],
            "block_id": assignment["block_id"],
            "run_number": assignment["run_number"],
            "anti_pattern_type": assignment["anti_pattern_type"],
            "symbol_name": assignment["symbol_name"],
            "context_level": assignment["context_level"],
            "trace_file": str(trace.resolve()),
            "trace_sha256": execution["trace_sha256"],
            "materialized": ref is not None,
        }
        if ref is None:
            index.append(
                base
                | {
                    "archive_path": None,
                    "materialized_source_ref": None,
                    "final_source_sha256": None,
                    "archive_tree_sha256": None,
                }
            )
            continue

        artifact = json.loads(ref.read_text(encoding="utf-8"))
        final_source = artifact["final_source"]
        if sha_text(final_source) != artifact["source_sha256"]:
            raise ValueError(f"materialized source hash mismatch: {ref}")
        relative_file = Path(artifact["relative_file"])
        pristine_file = args.corpus / relative_file
        if not pristine_file.exists():
            raise FileNotFoundError(pristine_file)
        pristine_source = pristine_file.read_text(encoding="utf-8-sig")
        if sha_text(pristine_source) != assignment["pristine_source_sha256"]:
            raise ValueError(f"pristine source drift: {pristine_file}")

        archive = args.out / f"{assignment['order']:04d}-{assignment['assignment_id']}"
        corpus_copy = archive / "corpus"
        copy_source_tree(args.corpus, corpus_copy)
        repaired_file = corpus_copy / relative_file
        repaired_file.parent.mkdir(parents=True, exist_ok=True)
        repaired_file.write_text(final_source, encoding="utf-8", newline="")
        if sha_text(repaired_file.read_text(encoding="utf-8")) != artifact["source_sha256"]:
            raise ValueError(f"archived source hash mismatch: {repaired_file}")

        diff = "".join(
            difflib.unified_diff(
                pristine_source.splitlines(keepends=True),
                final_source.splitlines(keepends=True),
                fromfile=f"pristine/{artifact['relative_file']}",
                tofile=f"repaired/{artifact['relative_file']}",
            )
        )
        metadata = base | {
            "campaign_id": manifest["campaign_id"],
            "relative_file": artifact["relative_file"],
            "materialized_source_ref": str(ref),
            "materialized_artifact_id": artifact["artifact_id"],
            "final_source_sha256": artifact["source_sha256"],
            "pristine_source_sha256": assignment["pristine_source_sha256"],
            "prompt_version": manifest["prompt_version"],
            "applier_prompt_version": manifest["applier_prompt_version"],
        }
        (archive / "ASSIGNMENT.json").write_text(
            json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        (archive / "REPAIR.diff").write_text(diff, encoding="utf-8", newline="")
        (archive / "README.txt").write_text(
            "Source-only reconstruction of one frozen grounding repair assignment.\n"
            "Open corpus/Corpus.sln to inspect or build the state. ASSIGNMENT.json records\n"
            "the condition; REPAIR.diff shows the production-code change.\n",
            encoding="utf-8",
            newline="\n",
        )
        tree_hash = write_tree_checksums(archive)
        index.append(
            base
            | {
                "archive_path": str(archive.resolve()),
                "materialized_source_ref": str(ref),
                "final_source_sha256": artifact["source_sha256"],
                "archive_tree_sha256": tree_hash,
            }
        )

    fields = list(index[0])
    with (args.out / "INDEX.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(index)
    (args.out / "INDEX.json").write_text(
        json.dumps(index, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    summary = {
        "campaign_id": manifest["campaign_id"],
        "completed_assignments": len(ledger),
        "materialized_codebases": sum(row["materialized"] for row in index),
        "non_materialized_assignments": sum(not row["materialized"] for row in index),
        "archive_contract": (
            "complete source-only corpus + repaired source + assignment metadata + "
            "unified diff + per-archive and outer checksums"
        ),
    }
    (args.out / "SUMMARY.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    outer = [
        f"{sha_bytes(path.read_bytes())}  {path.relative_to(args.out).as_posix()}"
        for path in sorted(args.out.rglob("*"), key=lambda item: item.relative_to(args.out).as_posix())
        if path.is_file() and path.name != "ARCHIVE_SHA256SUMS.txt"
    ]
    (args.out / "ARCHIVE_SHA256SUMS.txt").write_text(
        "\n".join(outer) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
