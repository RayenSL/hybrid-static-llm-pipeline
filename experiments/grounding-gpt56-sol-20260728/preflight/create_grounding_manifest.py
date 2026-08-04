#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
from collections import Counter
from pathlib import Path, PureWindowsPath

LEVELS = ["minimal", "structural", "relational", "full"]
TYPE_NAMES = {"god_class", "long_method", "obsolete_api_usage"}


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_hash(value: object, length: int = 24) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length]


def windows(path: Path) -> str:
    return subprocess.check_output(["wslpath", "-w", str(path.resolve())], text=True).strip()


def relative_from_corpus(raw: str) -> Path:
    parts = PureWindowsPath(raw).parts
    indexes = [i for i, part in enumerate(parts) if part.lower() == "corpus"]
    if not indexes:
        raise ValueError(f"file path has no corpus segment: {raw}")
    return Path(*parts[indexes[-1] + 1:])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--truth", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--applier", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--prompt-version", required=True)
    parser.add_argument("--applier-prompt-version", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.baseline.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if len(rows) != 30:
        raise ValueError(f"expected 30 baseline targets, found {len(rows)}")
    counts = Counter(row["anti_pattern_type"] for row in rows)
    if counts != Counter({name: 10 for name in TYPE_NAMES}):
        raise ValueError(f"unexpected anti-pattern baseline counts: {counts}")
    if len({(row["anti_pattern_type"], row["file_path"], row["symbol_name"], row["line"]) for row in rows}) != 30:
        raise ValueError("baseline target identities are not unique")
    if len({row["file_path"].lower() for row in rows}) != 30:
        raise ValueError("one-source-file-per-target requirement is not satisfied")

    truth = json.loads(args.truth.read_text(encoding="utf-8-sig"))
    projects = {
        project["name"]: {"Framework": ".NET 8", "Project": project["name"], "Domain": project["domain"]}
        for project in truth["projects"]
    }
    blocks = []
    for row in sorted(rows, key=lambda item: (item["anti_pattern_type"], item["symbol_name"])):
        relative = relative_from_corpus(row["file_path"])
        source = args.corpus / relative
        if not source.is_file():
            raise FileNotFoundError(source)
        project = relative.parts[1]
        if project not in projects:
            raise ValueError(f"missing project metadata for {project}")
        identity = {
            "anti_pattern_type": row["anti_pattern_type"],
            "file_path": row["file_path"],
            "symbol_name": row["symbol_name"],
            "line": row["line"],
        }
        blocks.append((stable_hash(identity), row, source, projects[project]))

    randomizer = random.Random(args.seed)
    randomizer.shuffle(blocks)
    assignments = []
    order = 0
    for block_id, row, source, metadata in blocks:
        levels = LEVELS.copy()
        randomizer.shuffle(levels)
        for level in levels:
            order += 1
            core = {
                "block_id": block_id,
                "run_number": 1,
                "context_level": level,
                "anti_pattern_type": row["anti_pattern_type"],
                "file_path": row["file_path"],
                "symbol_name": row["symbol_name"],
                "line": row["line"],
                "pristine_source_sha256": sha_file(source),
            }
            assignments.append({
                "order": order,
                "assignment_id": stable_hash(core),
                **core,
                "severity": row["severity"],
                "snippet": row.get("snippet"),
                "metrics": row.get("metrics") or {},
                "expected_quality_attributes": row.get("expected_quality_attributes") or [],
                "project_metadata": metadata,
            })

    manifest_core = {
        "schema_version": "1.0.0",
        "model_name": args.model,
        "applier_model": args.applier,
        "target_solution": windows(args.target),
        "baseline_source": windows(args.baseline),
        "baseline_sha256": sha_file(args.baseline),
        "code_revision": args.revision,
        "prompt_version": args.prompt_version,
        "applier_prompt_version": args.applier_prompt_version,
        "repetitions": 1,
        "randomization_seed": args.seed,
        "build_timeout_seconds": 180,
        "assignments": assignments,
    }
    manifest = {"campaign_id": stable_hash(manifest_core), **manifest_core}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "campaign_id": manifest["campaign_id"],
        "assignments": len(assignments),
        "targets": len(blocks),
        "counts": counts,
        "sha256": sha_file(args.out),
    }, default=dict, sort_keys=True))


if __name__ == "__main__":
    main()
