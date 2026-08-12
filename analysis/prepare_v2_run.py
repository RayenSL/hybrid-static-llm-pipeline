#!/usr/bin/env python3
"""Prepare and gate the v2 confirmatory experiment without making model calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVALUATED_TYPES = {"GodClass", "LongMethod"}
NEW_TARGETS = {f"{prefix}-{number:02d}" for prefix in ("GC", "LM") for number in range(11, 14)}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _review(path: Path) -> tuple[dict[str, bool | None], bool]:
    worksheet = _load(path)
    rows = worksheet.get("instances", [])
    verdicts = {row.get("instance_id"): row.get("valid") for row in rows}
    complete = (
        set(verdicts) == NEW_TARGETS
        and all(isinstance(value, bool) for value in verdicts.values())
        and all(str(row.get("semantic_note", "")).strip() for row in rows)
    )
    return verdicts, complete


def _oracle_counts(pipeline_root: Path) -> tuple[int, int, int, int]:
    plan = _load(pipeline_root / "layer3" / "ORACLE_PLAN_V2.json")
    evaluated = plan.get("evaluated_targets", [])
    obsolete = plan.get("obsolete_smoke_cases", [])
    if evaluated:
        evaluated_count = len(evaluated)
        cases_per_target = len(evaluated[0].get("cases", []))
        planned_cases = sum(len(target.get("cases", [])) for target in evaluated) + len(obsolete)
    else:
        evaluated_count = int(plan.get("evaluated_target_count", 0))
        cases_per_target = int(plan.get("cases_per_evaluated_target", 0))
        planned_cases = int(plan.get("expected_golden_file_count", 0))
    golden_count = len(list((pipeline_root / "layer3" / "golden").glob("*.golden")))
    return evaluated_count, cases_per_target, planned_cases, golden_count


def _baseline_matches_targets(path: Path, corpus_root: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    rows = []
    try:
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            if row.get("anti_pattern_type") in {"god_class", "long_method"}:
                rows.append(row)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False
    if len(rows) != 26:
        return False

    expected = _target_records(corpus_root)
    unmatched = rows.copy()
    for target in expected:
        target_path = str(Path(target["source_file"]).resolve()).lower()
        target_symbol = target["symbol_name"]
        match = next(
            (
                row
                for row in unmatched
                if str(Path(str(row.get("file_path", ""))).resolve()).lower() == target_path
                and (
                    target_symbol.endswith(str(row.get("symbol_name", "")))
                    or str(row.get("symbol_name", "")).endswith(target_symbol)
                )
                and row.get("line") == target["start_line"]
            ),
            None,
        )
        if match is None:
            return False
        snippet = match.get("snippet")
        if not isinstance(snippet, str) or not snippet.strip("\r\n"):
            return False
        declaration_lines = len(snippet.strip("\r\n").replace("\r\n", "\n").split("\n"))
        if int(match["line"]) + declaration_lines - 1 != target["end_line"]:
            return False
        unmatched.remove(match)
    return not unmatched


def assess_readiness(
    corpus_root: Path,
    pipeline_root: Path,
    experiment_root: Path | None = None,
) -> dict[str, Any]:
    """Return hard-gate outcomes. No input file is changed."""
    corpus_root = corpus_root.resolve()
    pipeline_root = pipeline_root.resolve()
    manifest = _load(corpus_root / "ground-truth" / "manifest.json")
    agreement = _load(corpus_root / "ground-truth" / "band-agreement-v2.0.json")
    r1, r1_complete = _review(corpus_root / "ground-truth" / "r1-worksheet-v2.0.json")
    r2, r2_complete = _review(corpus_root / "ground-truth" / "r2-worksheet-v2.0.json")
    evaluated_count, cases_per_target, planned_cases, golden_count = _oracle_counts(pipeline_root)

    totals = manifest.get("totals", {})
    band_summary = agreement.get("summary", {})
    reviews_agree = r1_complete and r2_complete and all(r1[key] == r2[key] for key in NEW_TARGETS)
    reviews_valid = reviews_agree and all(r1[key] is True for key in NEW_TARGETS)
    gates: dict[str, bool] = {
        "corpus_version_v2": manifest.get("corpus_version") == "v2.0",
        "balanced_target_inventory": (
            totals.get("god_class") == 13
            and totals.get("long_method") == 13
            and totals.get("obsolete_api") == 10
        ),
        "ground_truth_band_agreement": (
            agreement.get("release_gate_passed") is True
            and band_summary.get("instances_checked") == 36
            and band_summary.get("agreed") == 36
            and band_summary.get("disagreed") == 0
        ),
        "r1_semantic_review_complete": r1_complete,
        "r2_semantic_review_complete": r2_complete,
        "semantic_review_agreement": reviews_agree,
        "semantic_review_validity": reviews_valid,
        "private_oracle_plan": (
            evaluated_count == 26
            and cases_per_target == 10
            and planned_cases == 270
        ),
        "private_oracle_files": golden_count == 270,
    }

    preparation_gates: dict[str, bool] = {}
    if experiment_root is not None:
        experiment_root = experiment_root.resolve()
        baseline = experiment_root / "baseline.jsonl"
        generated = experiment_root / "generated-tests"
        artefacts = list(generated.glob("*.json")) if generated.is_dir() else []
        factorial = experiment_root / "factorial-manifest.json"
        preparation_gates = {
            "baseline_frozen": _baseline_matches_targets(baseline, corpus_root),
            "visible_test_generation_complete": len(artefacts) == 26,
            "factorial_manifest_frozen": factorial.is_file() and factorial.stat().st_size > 0,
        }

    failed = [name for name, passed in {**gates, **preparation_gates}.items() if not passed]
    release_failed = [name for name, passed in gates.items() if not passed]
    return {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "gates": gates,
        "preparation_gates": preparation_gates,
        "failed_gates": failed,
        "final_release_ready": not release_failed,
        "campaign_ready": not failed,
        "repair_execution_authorised": False,
        "repair_execution_note": "Preparation never authorises model calls; launch requires an explicit subsequent decision.",
    }


def _target_records(corpus_root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted((corpus_root / "ground-truth" / "records").glob("*.json")):
        record = _load(path)
        if record.get("anti_pattern") not in EVALUATED_TYPES:
            continue
        location = record["location"]
        relative = location["file"].replace("\\", "/")
        source = (corpus_root / "corpus" / relative).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"target source is missing: {source}")
        rows.append(
            {
                "instance_id": record["instance_id"],
                "anti_pattern": record["anti_pattern"],
                "source_file": str(source),
                "source_file_relative": f"corpus/{relative}",
                "symbol_name": location["symbol"],
                "start_line": int(location.get("line_start", location.get("start_line", 0))),
                "end_line": int(location.get("line_end", location.get("end_line", 0))),
                "source_sha256": _sha256(source),
            }
        )
    if len(rows) != 26:
        raise ValueError(f"expected 26 evaluated targets, found {len(rows)}")
    if len({row["source_file"] for row in rows}) != 26:
        raise ValueError("each evaluated target must have an independent source file")
    return rows


def build_run_spec(
    corpus_root: Path,
    pipeline_root: Path,
    *,
    corpus_revision: str,
    pipeline_revision: str,
    model_name: str,
    randomization_seed: int,
) -> dict[str, Any]:
    """Build the immutable design declaration; does not claim the run is ready."""
    if not corpus_revision.strip() or not pipeline_revision.strip():
        raise ValueError("both frozen repository revisions are required")
    targets = _target_records(corpus_root.resolve())
    oracle_plan = pipeline_root.resolve() / "layer3" / "ORACLE_PLAN_V2.json"
    return {
        "schema_version": "1.0.0",
        "experiment_kind": "confirmatory_v2_full_rerun",
        "status": "prepared_pending_hard_gates",
        "corpus": {
            "version": "v2.0",
            "revision": corpus_revision.strip(),
            "root": str(corpus_root.resolve()),
            "evaluated_inventory": {"GodClass": 13, "LongMethod": 13},
            "obsolete_inventory": 10,
        },
        "pipeline": {
            "revision": pipeline_revision.strip(),
            "root": str(pipeline_root.resolve()),
        },
        "model": {"key": model_name.strip()},
        "design": {
            "evaluated_targets": 26,
            "repetitions": 3,
            "factorial_cells": 8,
            "factorial_assignments": 26 * 3 * 8,
            "hybrid_comparator_conditions": 2,
            "hybrid_comparator_attempts": 26 * 3 * 2,
            "randomization_seed": randomization_seed,
            "iteration_budget": 6,
            "build_timeout_seconds": 180,
            "max_input_tokens": 120000,
        },
        "visible_tests": {
            "generation_calls_per_target": 2,
            "compile_correction_calls_max": 1,
            "cases_per_target": 5,
            "pristine_baseline_runs": 3,
            "generated_before_repair": True,
        },
        "private_oracle": {
            "plan": str(oracle_plan),
            "plan_sha256": _sha256(oracle_plan),
            "cases_per_evaluated_target": 10,
            "evaluated_cases": 260,
            "obsolete_smoke_cases": 10,
            "total_cases": 270,
            "visible_to_model": False,
        },
        "release_gate": {
            "r1": str(corpus_root.resolve() / "ground-truth" / "r1-worksheet-v2.0.json"),
            "r2": str(corpus_root.resolve() / "ground-truth" / "r2-worksheet-v2.0.json"),
            "band_agreement": str(corpus_root.resolve() / "ground-truth" / "band-agreement-v2.0.json"),
        },
        "targets": targets,
    }


def write_preparation(spec: dict[str, Any], output: Path, readiness: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=False)
    preflight = output / "preflight"
    preflight.mkdir()
    (output / "generated-tests").mkdir()
    (output / "campaign").mkdir()

    def write_json(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")

    write_json(output / "RUN_SPEC.json", spec)
    write_json(preflight / "TARGETS.json", spec["targets"])
    write_json(
        output / "test-generation-plan.json",
        {
            "status": "not_started",
            "cases_per_target": 5,
            "targets": [
                {
                    "instance_id": target["instance_id"],
                    "source_file": target["source_file"],
                    "symbol_name": target["symbol_name"],
                    "artifact_status": "pending",
                }
                for target in spec["targets"]
            ],
        },
    )
    write_json(output / "RUN_READINESS.json", readiness)


def refresh_readiness(corpus_root: Path, pipeline_root: Path, experiment_root: Path) -> dict[str, Any]:
    """Re-evaluate the hard gates and replace only the derived readiness report."""
    report = assess_readiness(corpus_root, pipeline_root, experiment_root)
    path = experiment_root.resolve() / "RUN_READINESS.json"
    if not path.parent.is_dir():
        raise FileNotFoundError(f"experiment directory is missing: {path.parent}")
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--pipeline", type=Path, required=True)
    parser.add_argument("--corpus-revision")
    parser.add_argument("--pipeline-revision")
    parser.add_argument("--model")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    if args.refresh:
        readiness = refresh_readiness(args.corpus, args.pipeline, args.out)
        print(json.dumps({"output": str(args.out.resolve()), "failed_gates": readiness["failed_gates"]}))
        return 0

    missing = [
        name
        for name, value in (
            ("--corpus-revision", args.corpus_revision),
            ("--pipeline-revision", args.pipeline_revision),
            ("--model", args.model),
            ("--seed", args.seed),
        )
        if value is None or value == ""
    ]
    if missing:
        parser.error(f"required unless --refresh: {', '.join(missing)}")

    spec = build_run_spec(
        args.corpus,
        args.pipeline,
        corpus_revision=args.corpus_revision,
        pipeline_revision=args.pipeline_revision,
        model_name=args.model,
        randomization_seed=args.seed,
    )
    readiness = assess_readiness(args.corpus, args.pipeline, args.out)
    write_preparation(spec, args.out, readiness)
    print(json.dumps({"output": str(args.out.resolve()), "failed_gates": readiness["failed_gates"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
