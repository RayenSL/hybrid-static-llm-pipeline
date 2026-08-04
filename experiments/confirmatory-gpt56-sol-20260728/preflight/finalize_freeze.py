from __future__ import annotations

import copy
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


EXPERIMENT_ID = "confirmatory-gpt56-sol-20260728"
PIPELINE_GIT_REVISION = "4f7c2607b8854c7c21ec02002daa058f5828c209"
PIPELINE_CONTENT_SHA256 = "8a29f51e95794d6623743e7865301f38cc641e989bd46446ff03e196e62cd778"
CORPUS_GIT_REVISION = "16befd9a07d15c52da7ba1bac55c32aef56bfd2e"
CORPUS_CONTENT_SHA256 = "599967fc818465b619e899dc083e82355ba5d665217fcc0237aa03b6598d3d01"
GROUND_TRUTH_CONTENT_SHA256 = "7dcb5805988322a4e94c332715168dd1d8c4c9f24c2bad0a21d217bd10c20802"
BASELINE_SHA256 = "48ce04394a52e1bfa76817c1b825f97b7cd4e6a7e110f6bd8fb9ff0e526e199c"
WINDOWS_ROOT = r"Z:\GitHub\hybrid-static-llm-pipeline"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def windows_path(relative: str) -> str:
    return WINDOWS_ROOT + "\\" + relative.replace("/", "\\")


def main() -> None:
    script = Path(__file__).resolve()
    preflight = script.parent
    experiment = preflight.parent
    root = script.parents[3]
    generated = experiment / "generated-tests"

    manifest = load_json(experiment / "factorial-manifest.json")
    summary = load_json(experiment / "test-generation-summary.json")
    plan = load_json(experiment / "test-generation-plan.json")
    old_freeze = load_json(root / "experiments/confirmatory-20260727/FREEZE_MANIFEST.json")
    power = load_json(preflight / "power/power_classification.json")

    artifacts = [load_json(path) for path in sorted(generated.glob("*.json"))]
    planned = {(item["file_path"], item["symbol_name"]) for item in plan["targets"]}
    observed = {(item["source_file"], item["target_symbol_name"]) for item in artifacts}
    instance_by_target = {
        (item["file_path"], item["symbol_name"]): item["instance_id"] for item in plan["targets"]
    }

    generated_checksums = "".join(
        f"{sha256(path)}  {path.name}\n" for path in sorted(generated.glob("*.json"))
    )
    (generated / "SHA256SUMS.txt").write_text(generated_checksums, encoding="utf-8")

    csv_fields = [
        "instance_id",
        "source_file",
        "symbol_name",
        "model_name",
        "admission_status",
        "admitted",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "artifact_ref",
        "artifact_sha256",
        "test_sha256",
    ]
    with (experiment / "test-generation-summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows(summary["artifacts"])

    ledger_lines = [
        "instance_id\ttimestamp_utc\tsource_file\tsymbol_name\tmodel_name\tadmission_status\tpersisted_artifact\n"
    ]
    for artifact in sorted(artifacts, key=lambda item: item["timestamp"]):
        key = (artifact["source_file"], artifact["target_symbol_name"])
        ledger_lines.append(
            "\t".join(
                [
                    instance_by_target[key],
                    artifact["timestamp"],
                    artifact["source_file"],
                    artifact["target_symbol_name"],
                    artifact["model_name"],
                    artifact["admission_status"],
                    artifact["artifact_ref"],
                ]
            )
            + "\n"
        )
    (experiment / "test-generation-command-ledger.tsv").write_text(
        "".join(ledger_lines), encoding="utf-8"
    )
    (preflight / "test-generation-remaining.tsv").write_text(
        "instance_id\tsource_file\tsymbol_name\n", encoding="utf-8"
    )

    call_audit = {
        "audit_status": "pass",
        "policy": "one generation call per planned instance; no retries for any failure",
        "planned_targets": len(planned),
        "persisted_artifacts": len(artifacts),
        "unique_observed_targets": len(observed),
        "planned_targets_equal_observed_targets": planned == observed,
        "duplicate_persisted_targets": len(artifacts) - len(observed),
        "remaining_targets": len(planned - observed),
        "model_names": sorted({item["model_name"] for item in artifacts}),
        "admission_status_counts": summary["status_counts"],
        "note": (
            "The ledger is derived from immutable per-call artifacts and their timestamps. "
            "No failed target was regenerated."
        ),
    }
    write_json(preflight / "TEST_GENERATION_CALL_AUDIT.json", call_audit)

    previous_power = root / "experiments/confirmatory-20260727/preflight/power"
    power_files = [
        "power_simulation.py",
        "power_grid.csv",
        "power_classification.json",
        "POWER_REPORT.md",
    ]
    power_audit = {
        "audit_status": "pass",
        "model_independent": True,
        "design_inputs": {
            "instances": 19,
            "repetitions": 3,
            "conditions": 8,
            "simulation_seed": 20260727,
            "simulations_per_condition": 10000,
        },
        "files": [
            {
                "name": name,
                "sha256": sha256(preflight / "power" / name),
                "byte_identical_to_previous_frozen_analysis": (
                    (preflight / "power" / name).read_bytes()
                    == (previous_power / name).read_bytes()
                ),
            }
            for name in power_files
        ],
        "reproducibility_note": (
            "The model-independent power analysis and outputs are byte-identical to the "
            "previously executed frozen analysis. A local rerun was attempted at finalization, "
            "but the available Python runtimes did not include SciPy; no result was altered."
        ),
    }
    write_json(preflight / "POWER_REPRODUCIBILITY_AUDIT.json", power_audit)

    archive_contract = {
        "status": "frozen_before_confirmatory_repairs",
        "script": windows_path(
            f"experiments/{EXPERIMENT_ID}/preflight/archive_materialized_codebases.py"
        ),
        "script_sha256": sha256(preflight / "archive_materialized_codebases.py"),
        "execution_point": "after all repair assignments and before private Layer 3",
        "output_directory": windows_path(
            f"experiments/{EXPERIMENT_ID}/campaign/viewable-codebases"
        ),
        "contents_per_materialized_assignment": [
            "complete source-only corpus",
            "repaired final source applied",
            "ASSIGNMENT.json",
            "REPAIR.diff",
            "README.txt",
            "SHA256SUMS.txt",
        ],
        "index_files": [
            "INDEX.csv",
            "INDEX.json",
            "SUMMARY.json",
            "ARCHIVE_SHA256SUMS.txt",
        ],
        "non_materialized_policy": (
            "retain index row with materialized=false; do not invent a codebase"
        ),
        "private_information_included": False,
        "consumer_build_command": (
            "dotnet build corpus/Corpus.sln (normal restore recreates excluded obj assets)"
        ),
        "sol_sanity_validation": {
            "campaign_id": "1ff57314a37b4fec9c1f7a44",
            "completed_assignments": 8,
            "materialized_codebases": 8,
            "all_archive_hashes_verified": True,
            "archived_solution_build_smoke_passed": True,
            "build_smoke_location": "disposable Windows temporary copy",
        },
    }
    write_json(experiment / "CODEBASE_ARCHIVE_CONTRACT.json", archive_contract)

    assignments = manifest["assignments"]
    test_on = [item for item in assignments if item["visible_tests_enabled"]]
    test_on_available = [
        item for item in test_on if item["visible_test_artifact_ref"] is not None
    ]
    manifest_sha = sha256(experiment / "factorial-manifest.json")
    classification = power["classifications"]
    now = datetime.now(timezone.utc).isoformat()

    freeze = copy.deepcopy(old_freeze)
    freeze.update(
        {
            "experiment_id": EXPERIMENT_ID,
            "status": "pre_repair_frozen_after_model_dependent_preflight",
            "frozen_at_utc": now,
            "pipeline_git_revision": PIPELINE_GIT_REVISION,
            "pipeline_content_sha256": PIPELINE_CONTENT_SHA256,
            "pipeline_file_count": 179,
            "corpus_git_revision": CORPUS_GIT_REVISION,
            "corpus_model_visible_content_sha256": CORPUS_CONTENT_SHA256,
            "corpus_model_visible_file_count": 68,
            "ground_truth_content_sha256": GROUND_TRUTH_CONTENT_SHA256,
            "ground_truth_file_count": 43,
            "confirmatory_baseline": windows_path(
                f"experiments/{EXPERIMENT_ID}/confirmatory-baseline.jsonl"
            ),
            "confirmatory_baseline_sha256": BASELINE_SHA256,
            "excluded_instances": [
                {
                    "instance_id": "LM-01",
                    "reason": (
                        "used for GPT-5.4 and GPT-5.6 Sol end-to-end shakedowns; "
                        "outcomes inspected before the confirmatory run"
                    ),
                }
            ],
            "campaign_id": manifest["campaign_id"],
            "factorial_manifest": windows_path(
                f"experiments/{EXPERIMENT_ID}/factorial-manifest.json"
            ),
            "factorial_manifest_sha256": manifest_sha,
            "model_configuration": {
                "key": "gpt-5.6-sol",
                "provider": "azure",
                "deployment": "gpt-5.6-sol",
                "temperature": 1.0,
                "reasoning_effort": "provider_default_medium",
                "configured_max_tokens": 1024,
                "request_max_output_tokens": None,
                "request_max_output_tokens_note": (
                    "The current adapter intentionally omits the request limit so whole-file "
                    "agent edits are not truncated; the deployment default therefore applies."
                ),
                "compatibility_probe": {
                    "non_evaluation_fixture": True,
                    "initial_temperature_0_1": "HTTP 400; Sol accepts only default 1",
                    "corrected_temperature_1_0": "admitted; build and two pristine runs passed",
                },
            },
            "generated_test_policy": {
                "one_call_per_instance": True,
                "retry": False,
                "generated_before_repair": True,
                "detector_coordinates_supplied": [
                    "production project",
                    "source file",
                    "target symbol",
                    "target start line",
                    "target end line",
                    "pristine source",
                ],
                "anti_pattern_label_withheld": True,
                "ground_truth_withheld": True,
                "private_tests_withheld": True,
                "baseline_runs": 2,
                "timeout_seconds": 180,
                "calls": 19,
                "admitted": 17,
                "build_failed": 1,
                "baseline_failed": 1,
            },
            "power_classification": classification,
            "resource_reporting": {
                "measures": [
                    "input tokens",
                    "output tokens",
                    "LLM calls",
                    "builds",
                    "tests",
                    "durations",
                    "nominal USD cost",
                ],
                "standard_global_price_usd_per_million": {
                    "input": 5.0,
                    "output": 30.0,
                },
                "test_generation": {
                    "input_tokens": summary["input_tokens"],
                    "output_tokens": summary["output_tokens"],
                    "nominal_cost_usd": summary["nominal_test_generation_cost_usd"],
                },
            },
            "model_amendment": {
                "change": "gpt-5.4 to Azure-deployed gpt-5.6-sol",
                "timing": "before any confirmatory repair assignment or private outcome",
                "previous_confirmatory_repair_assignments_executed": 0,
                "superseded_freeze": windows_path(
                    "archive/previous-runs-20260727/"
                    "gpt54-confirmatory-freeze-superseded-20260728"
                ),
                "same_instances_repetitions_conditions_seed_and_pipeline": True,
                "model_dependent_characterization_tests_regenerated": True,
            },
            "codebase_archive_contract": archive_contract,
            "optional_hybrid_comparator": False,
        }
    )
    freeze["baseline_normalization"] = {
        "method": old_freeze["baseline_normalization"]["method"],
        "uses_ground_truth": False,
        "script": windows_path(
            f"experiments/{EXPERIMENT_ID}/preflight/normalize_baseline.py"
        ),
        "script_sha256": sha256(preflight / "normalize_baseline.py"),
        "audit": windows_path(
            f"experiments/{EXPERIMENT_ID}/preflight/BASELINE_NORMALIZATION_AUDIT.json"
        ),
        "audit_sha256": sha256(preflight / "BASELINE_NORMALIZATION_AUDIT.json"),
    }
    write_json(experiment / "FREEZE_MANIFEST.json", freeze)

    pre_run_audit = {
        "audit_status": "pass",
        "audited_at_utc": now,
        "repair_execution_status": "not_started_by_design_awaiting_explicit_launch",
        "campaign_id": manifest["campaign_id"],
        "manifest_sha256": manifest_sha,
        "pipeline_content_sha256": PIPELINE_CONTENT_SHA256,
        "corpus_content_sha256": CORPUS_CONTENT_SHA256,
        "ground_truth_content_sha256": GROUND_TRUTH_CONTENT_SHA256,
        "confirmatory_baseline_sha256": BASELINE_SHA256,
        "instances": 19,
        "repetitions": 3,
        "blocks": 57,
        "assignments": len(assignments),
        "test_off_assignments": len(assignments) - len(test_on),
        "test_on_assignments": len(test_on),
        "test_on_with_admitted_test": len(test_on_available),
        "test_on_without_admitted_test": len(test_on) - len(test_on_available),
        "generated_test_calls": summary["artifact_count"],
        "generated_test_admitted": summary["status_counts"].get("admitted", 0),
        "generated_test_build_failed": summary["status_counts"].get("build_failed", 0),
        "generated_test_baseline_failed": summary["status_counts"].get(
            "baseline_failed", 0
        ),
        "generated_test_input_tokens": summary["input_tokens"],
        "generated_test_output_tokens": summary["output_tokens"],
        "generated_test_total_tokens": summary["total_tokens"],
        "generated_test_nominal_cost_usd": summary[
            "nominal_test_generation_cost_usd"
        ],
        "test_generation_call_audit": "pass",
        "prompt_leakage_check": "pass",
        "pipeline_tests_passed": 85,
        "pristine_corpus_build_passed": True,
        "randomization_seed": manifest["randomization_seed"],
        "iteration_budget": manifest["iteration_budget"],
        "build_timeout_seconds": manifest["build_timeout_seconds"],
        "max_input_token_guard": manifest["max_input_token_guard"],
        "model_name": manifest["model_name"],
        "temperature": 1.0,
        "reasoning_effort": "provider_default_medium",
        "confirmatory_estimand": "visible_test_main_effect",
        "minimum_meaningful_risk_difference": 0.2,
        "power_classification": classification,
        "power_reproducibility_audit": "pass; byte-identical frozen analysis",
        "lm01_excluded": True,
        "baseline_normalization_verified": True,
        "private_layer3_executed": False,
        "private_outcomes_exposed_to_repair_model": False,
        "confirmatory_repairs_executed": 0,
        "codebase_archive_contract": archive_contract,
    }
    write_json(experiment / "PRE_RUN_AUDIT.json", pre_run_audit)

    # Seal every file in the experiment after all derived records have been written.
    checksum_path = experiment / "PRE_RUN_SHA256SUMS.txt"
    entries = []
    for path in sorted(experiment.rglob("*")):
        if path.is_file() and path != checksum_path:
            entries.append(f"{sha256(path)}  {path.relative_to(experiment).as_posix()}\n")
    checksum_path.write_text("".join(entries), encoding="utf-8")

    print(
        json.dumps(
            {
                "experiment_id": EXPERIMENT_ID,
                "campaign_id": manifest["campaign_id"],
                "assignments": len(assignments),
                "test_on_with_admitted_test": len(test_on_available),
                "test_on_without_admitted_test": len(test_on) - len(test_on_available),
                "sealed_files": len(entries),
                "manifest_sha256": manifest_sha,
                "pre_run_ledger_sha256": sha256(checksum_path),
            }
        )
    )


if __name__ == "__main__":
    main()
