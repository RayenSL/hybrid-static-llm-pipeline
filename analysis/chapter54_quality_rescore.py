#!/usr/bin/env python3
"""Offline whole-solution quality remeasurement for frozen factorial archives.

The script never edits an archived codebase. Each worker owns a temporary copy of
the pristine corpus, keeps the analyzer configuration installed, substitutes one
frozen repaired file at a time, rebuilds, scans, restores the pristine file, and
records the exact before/after QualityDelta fields used by the thesis instrument.
No LLM or private behavioral oracle is invoked.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path


DIRECTORY_BUILD_PROPS = """<Project>
  <!-- Temporary Layer 2 analyzer configuration for Chapter 5.4 remeasurement. -->
  <PropertyGroup>
    <EnableNETAnalyzers>true</EnableNETAnalyzers>
    <AnalysisLevel>8.0-all</AnalysisLevel>
    <ErrorLog>$(MSBuildProjectDirectory)\\$(MSBuildProjectName).sarif,version=2.1</ErrorLog>
  </PropertyGroup>
</Project>
"""

SKIP_DIRS = {"bin", "obj", ".git", ".vs", ".idea"}
TYPE_NAME = {
    "god_class": "GodClass",
    "long_method": "LongMethod",
    "obsolete_api_usage": "ObsoleteApiUsage",
}


def copy_pristine(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(*SKIP_DIRS),
    )


def run(command: list[str], *, cwd: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def scan_state(
    *, dotnet: Path, cli: Path, solution: Path, root: Path, output: Path, timeout: int
) -> dict:
    result = run(
        [
            str(dotnet),
            str(cli),
            "quality-scan",
            "--target",
            str(solution),
            "--sarif-root",
            str(root),
            "--output",
            str(output),
        ],
        cwd=root,
        timeout=timeout,
    )
    if result.returncode != 0 or not output.is_file():
        raise RuntimeError(
            f"quality-scan failed ({result.returncode})\n{result.stdout[-4000:]}"
        )
    return json.loads(output.read_text(encoding="utf-8-sig"))


def diff_counts(before: dict, after: dict) -> dict:
    keys = set(before) | set(after)
    return {
        key: int(after.get(key, 0)) - int(before.get(key, 0))
        for key in sorted(keys)
        if int(after.get(key, 0)) - int(before.get(key, 0)) != 0
    }


def normalise(value: str) -> str:
    return value.replace("\\", "/").lstrip("/")


def quality_delta(before: dict, after: dict, anti_pattern: str, relative_file: str) -> dict:
    smell_delta = diff_counts(
        before.get("smell_counts_by_type", {}),
        after.get("smell_counts_by_type", {}),
    )
    before_smells = set(before.get("smell_keys", []))
    after_smells = set(after.get("smell_keys", []))
    targeted_type = TYPE_NAME[anti_pattern]
    repaired = normalise(relative_file)
    collateral = False
    for key in before_smells ^ after_smells:
        parts = key.split("|")
        finding_type = parts[0] if parts else ""
        finding_file = normalise(parts[1]) if len(parts) > 1 else ""
        if finding_type != targeted_type or finding_file.lower() != repaired.lower():
            collateral = True
            break

    before_diagnostics = {row["key"] for row in before.get("diagnostics", [])}
    after_diagnostics = {row["key"] for row in after.get("diagnostics", [])}
    ca_available = bool(before.get("ca_available") and after.get("ca_available"))
    return {
        "smell_delta_by_type": smell_delta,
        "smell_total_delta": int(after["smell_total"]) - int(before["smell_total"]),
        "smell_collateral": collateral,
        "ca_headline_delta_by_category": diff_counts(
            before.get("ca_headline_by_category", {}),
            after.get("ca_headline_by_category", {}),
        ),
        "ca_headline_total_delta": int(after["ca_headline_total"])
        - int(before["ca_headline_total"]),
        "ca_all_delta_by_category": diff_counts(
            before.get("ca_all_by_category", {}),
            after.get("ca_all_by_category", {}),
        ),
        "ca_all_total_delta": int(after["ca_all_total"]) - int(before["ca_all_total"]),
        "compiler_obsolete_delta": int(after["compiler_obsolete_count"])
        - int(before["compiler_obsolete_count"]),
        "ca_introduced": sorted(after_diagnostics - before_diagnostics)
        if ca_available
        else [],
        "ca_removed": sorted(before_diagnostics - after_diagnostics)
        if ca_available
        else [],
        "ca_available": ca_available,
    }


def build_once(dotnet: Path, solution: Path, root: Path, timeout: int) -> subprocess.CompletedProcess:
    return run(
        [
            str(dotnet),
            "build",
            str(solution),
            "--nologo",
            "--verbosity",
            "quiet",
        ],
        cwd=root,
        timeout=timeout,
    )


def worker(
    worker_id: int,
    assignments: list[dict],
    *,
    corpus: Path,
    dotnet: Path,
    cli: Path,
    timeout: int,
    checkpoint,
    lock: threading.Lock,
    progress: dict,
) -> None:
    work = Path(tempfile.gettempdir()) / (
        f"hybridlens-ch54-quality-worker-{worker_id}-{uuid.uuid4().hex}"
    )
    copy_pristine(corpus, work)
    props = work / "Directory.Build.props"
    props.write_text(DIRECTORY_BUILD_PROPS, encoding="utf-8")
    solution = work / "Corpus.sln"
    scan_file = work / "chapter54-quality-scan.json"
    try:
        baseline_build = build_once(dotnet, solution, work, timeout)
        if baseline_build.returncode != 0:
            raise RuntimeError(
                f"worker {worker_id} baseline build failed\n{baseline_build.stdout[-4000:]}"
            )
        baseline = scan_state(
            dotnet=dotnet,
            cli=cli,
            solution=solution,
            root=work,
            output=scan_file,
            timeout=timeout,
        )

        for item in assignments:
            archive = Path(item["archive_path"])
            assignment = json.loads(
                (archive / "ASSIGNMENT.json").read_text(encoding="utf-8-sig")
            )
            relative_file = assignment["relative_file"].replace("/", os.sep)
            repaired = archive / "corpus" / relative_file
            pristine = corpus / relative_file
            target = work / relative_file
            shutil.copy2(repaired, target)
            os.utime(target, None)
            started = time.perf_counter()
            build = build_once(dotnet, solution, work, timeout)
            after = scan_state(
                dotnet=dotnet,
                cli=cli,
                solution=solution,
                root=work,
                output=scan_file,
                timeout=timeout,
            )
            delta = quality_delta(
                baseline, after, item["anti_pattern_type"], assignment["relative_file"]
            )
            shutil.copy2(pristine, target)
            os.utime(target, None)
            result = {
                **item,
                "relative_file": assignment["relative_file"],
                "analyzer_build_passed": build.returncode == 0,
                "quality_delta": delta,
                "after_scan": {
                    "smell_total": after["smell_total"],
                    "ca_headline_total": after["ca_headline_total"],
                    "ca_all_total": after["ca_all_total"],
                    "compiler_obsolete_count": after["compiler_obsolete_count"],
                    "ca_available": after["ca_available"],
                },
                "duration_seconds": round(time.perf_counter() - started, 3),
            }
            with lock:
                checkpoint.write(json.dumps(result, separators=(",", ":")) + "\n")
                checkpoint.flush()
                progress["done"] += 1
                if progress["done"] % 10 == 0 or progress["done"] == progress["total"]:
                    print(
                        f"quality remeasurement: {progress['done']}/{progress['total']}",
                        flush=True,
                    )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--dotnet", required=True, type=Path)
    parser.add_argument("--cli", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    assignments = json.loads(args.index.read_text(encoding="utf-8-sig"))
    if args.limit > 0:
        assignments = assignments[: args.limit]
    expected_ids = {row["assignment_id"] for row in assignments}
    checkpoint_path = args.out.with_suffix(args.out.suffix + ".checkpoint")
    completed: dict[str, dict] = {}
    if checkpoint_path.is_file():
        for line in checkpoint_path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                row = json.loads(line)
                completed[row["assignment_id"]] = row
    remaining = [row for row in assignments if row["assignment_id"] not in completed]
    args.out.parent.mkdir(parents=True, exist_ok=True)

    lock = threading.Lock()
    progress = {
        "done": len(completed),
        "total": len(assignments),
    }
    partitions = [[] for _ in range(max(1, min(args.parallel, len(remaining) or 1)))]
    for index, row in enumerate(remaining):
        partitions[index % len(partitions)].append(row)
    with checkpoint_path.open("a", encoding="utf-8", buffering=1) as checkpoint:
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(partitions)) as pool:
            futures = [
                pool.submit(
                    worker,
                    worker_id,
                    rows,
                    corpus=args.corpus,
                    dotnet=args.dotnet,
                    cli=args.cli,
                    timeout=args.timeout,
                    checkpoint=checkpoint,
                    lock=lock,
                    progress=progress,
                )
                for worker_id, rows in enumerate(partitions)
                if rows
            ]
            for future in futures:
                future.result()

    final: dict[str, dict] = {}
    for line in checkpoint_path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            row = json.loads(line)
            final[row["assignment_id"]] = row
    if set(final) != expected_ids:
        missing = expected_ids - set(final)
        extra = set(final) - expected_ids
        raise RuntimeError(f"checkpoint mismatch: missing={len(missing)} extra={len(extra)}")
    ordered = sorted(final.values(), key=lambda row: row["order"])
    args.out.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in ordered),
        encoding="utf-8",
    )
    checkpoint_path.unlink()
    print(
        json.dumps(
            {
                "status": "complete",
                "rows": len(ordered),
                "output": str(args.out),
                "sha256": sha256(args.out),
                "analyzer_build_failures": sum(
                    not row["analyzer_build_passed"] for row in ordered
                ),
                "ca_unavailable": sum(
                    not row["quality_delta"]["ca_available"] for row in ordered
                ),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
