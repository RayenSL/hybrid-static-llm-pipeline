from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def verify_ledger(path: Path, root: Path) -> int:
    count = 0
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        if not raw.strip():
            continue
        expected, relative = raw.split("  ", 1)
        target = root / relative
        if not target.is_file() or sha256(target) != expected:
            raise RuntimeError(f"checksum mismatch: {target}")
        count += 1
    return count


def main() -> None:
    script = Path(__file__).resolve()
    experiment = script.parent.parent
    repo = experiment.parent.parent
    results = experiment / "results"
    private_path = experiment / "private-results/layer3-campaign.jsonl"

    pre_private_count = verify_ledger(
        experiment / "POST_REPAIR_FREEZE_SHA256SUMS.txt", experiment
    )
    campaign_core_count = verify_ledger(
        experiment / "campaign/CORE_SHA256SUMS.txt", experiment / "campaign"
    )

    private = [
        json.loads(line)
        for line in private_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if len(private) != 456:
        raise RuntimeError("private result count is not 456")
    if len({row["evaluation_id"] for row in private}) != 456:
        raise RuntimeError("private evaluation IDs are not unique")
    if len({PureWindowsPath(row["artifact_ref"]).name for row in private}) != 456:
        raise RuntimeError("private artifact refs are not unique")
    if any(not row["evaluated"] or row["not_run_reason"] is not None for row in private):
        raise RuntimeError("private evaluation contains not-run results")
    if Counter(row["passed"] for row in private) != Counter({True: 447, False: 9}):
        raise RuntimeError("unexpected private pass/regression totals")
    if {row["oracle_manifest_version"] for row in private} != {"1.0.0"}:
        raise RuntimeError("unexpected oracle version")
    if any((row["passing_drivers"], row["failing_drivers"]) not in {(30, 0), (29, 1)}
           for row in private):
        raise RuntimeError("unexpected private driver totals")

    attempts_path = results / "attempts.json"
    attempts = load_json(attempts_path)
    arms = load_json(results / "arm_summary.json")
    if len(attempts) != 456 or len(arms) != 8:
        raise RuntimeError("unexpected summary dimensions")
    if any(
        row["strict_success"]
        != (row["build_passed"] and row["metric_resolved"] and row["private_test_passed"])
        for row in attempts
    ):
        raise RuntimeError("strict-success derivation mismatch")
    arm_counts = Counter(
        (row["grounding_enabled"], row["control_structure"], row["visible_tests_enabled"])
        for row in attempts
    )
    if len(arm_counts) != 8 or set(arm_counts.values()) != {57}:
        raise RuntimeError("factorial arms are not balanced")

    chapter54 = results / "chapter5_4"
    quality_rows = [
        json.loads(line)
        for line in (chapter54 / "quality-rescore.jsonl").read_text(
            encoding="utf-8-sig"
        ).splitlines()
        if line.strip()
    ]
    if len(quality_rows) != 456:
        raise RuntimeError("Chapter 5.4 quality remeasurement count is not 456")
    if len({row["assignment_id"] for row in quality_rows}) != 456:
        raise RuntimeError("Chapter 5.4 quality assignment IDs are not unique")
    if any(
        not row["analyzer_build_passed"]
        or not row["quality_delta"]["ca_available"]
        for row in quality_rows
    ):
        raise RuntimeError("Chapter 5.4 quality remeasurement is incomplete")
    if not any(
        row["quality_delta"]["ca_all_total_delta"] != 0
        for row in quality_rows
    ):
        raise RuntimeError("Chapter 5.4 CA all-rules deltas are unexpectedly all zero")
    pristine_quality = load_json(chapter54 / "pristine-quality-scan.json")
    if (
        pristine_quality["smell_total"] != 30
        or pristine_quality["smell_counts_by_type"]
        != {"GodClass": 10, "LongMethod": 10, "ObsoleteApiUsage": 10}
        or not pristine_quality["ca_available"]
    ):
        raise RuntimeError("unexpected Chapter 5.4 pristine quality baseline")
    package = chapter54 / "package"
    expected_package_counts = {
        "tables_csv": len(list((package / "tables").glob("table5_*.csv"))),
        "tables_md": len(list((package / "tables").glob("table5_*.md"))),
        "tables_tex": len(list((package / "tables").glob("table5_*.tex"))),
        "figures_png": len(list((package / "figures").glob("figure5_*.png"))),
        "figures_svg": len(list((package / "figures").glob("figure5_*.svg"))),
        "figures_pdf": len(list((package / "figures").glob("figure5_*.pdf"))),
    }
    if expected_package_counts != {
        "tables_csv": 15,
        "tables_md": 15,
        "tables_tex": 15,
        "figures_png": 7,
        "figures_svg": 7,
        "figures_pdf": 7,
    }:
        raise RuntimeError(f"incomplete Chapter 5.4 package: {expected_package_counts}")

    strict = sum(row["strict_success"] for row in attempts)
    private_passes = sum(row["private_test_passed"] for row in attempts)
    builds = sum(row["build_passed"] for row in attempts)
    resolved = sum(row["metric_resolved"] for row in attempts)
    if (strict, private_passes, builds, resolved) != (423, 447, 456, 432):
        raise RuntimeError("canonical totals changed")
    regressions = [row for row in attempts if not row["private_test_passed"]]
    regression_instances = {row["instance_key"] for row in regressions}
    if len(regression_instances) != 1 or "VatResolver.Resolve" not in next(iter(regression_instances)):
        raise RuntimeError("regression concentration changed")

    risk_rows = list(csv.DictReader(
        (results / "paired-analysis/paired_risk_differences.csv").open(encoding="utf-8-sig")
    ))
    primary = next(row for row in risk_rows if row["contrast"] == "visible_test_main")
    paired_meta = load_json(results / "paired-analysis/ANALYSIS_METADATA.json")
    glmm_meta = load_json(results / "glmm-analysis/GLMM_METADATA.json")
    if paired_meta["strict_successes"] != strict:
        raise RuntimeError("paired analysis mismatch")
    if glmm_meta["analysis_seed"] != 20260728:
        raise RuntimeError("unexpected GLMM seed")
    if not glmm_meta["primary_model_fit"]["optimizer"]["success"]:
        raise RuntimeError("regularized MAP GLMM did not converge")
    if not glmm_meta["sensitivity_model_fit"]["optimizer"]["success"]:
        raise RuntimeError("regularized VB GLMM did not converge")

    test_generation = load_json(experiment / "test-generation-summary.json")
    repair_audit = load_json(experiment / "POST_REPAIR_AUDIT.json")
    resources = {
        "model_calls": repair_audit["resources"]["llm_calls"] + test_generation["artifact_count"],
        "input_tokens": repair_audit["resources"]["input_tokens"] + test_generation["input_tokens"],
        "output_tokens": repair_audit["resources"]["output_tokens"] + test_generation["output_tokens"],
        "total_tokens": repair_audit["resources"]["total_tokens"] + test_generation["total_tokens"],
        "test_generation_cost_usd": test_generation["nominal_test_generation_cost_usd"],
        "repair_campaign_cost_usd": repair_audit["resources"]["nominal_cost_usd"],
        "combined_nominal_cost_usd": round(
            test_generation["nominal_test_generation_cost_usd"]
            + repair_audit["resources"]["nominal_cost_usd"], 6
        ),
        "private_layer3_model_calls": 0,
    }

    credential_patterns = [
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+"),
        re.compile(r"(?i)(api[_ -]?key|access[_ -]?token)\s*[=:]\s*[A-Za-z0-9_./+-]{20,}"),
    ]
    scan_paths = [
        private_path,
        *[p for p in results.rglob("*") if p.is_file() and "archive" not in p.parts],
        experiment / "EXPERIMENT_REPORT.md",
        experiment / "DEVIATIONS.md",
    ]
    hits = [
        p.relative_to(repo).as_posix()
        for p in scan_paths
        if any(pattern.search(p.read_text(encoding="utf-8-sig", errors="ignore"))
               for pattern in credential_patterns)
    ]
    if hits:
        raise RuntimeError("credential-shaped value found in final artifacts")

    audit = {
        "audit_status": "pass",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_id": repair_audit["campaign_id"],
        "pre_private_freeze_entries_verified": pre_private_count,
        "campaign_core_entries_verified": campaign_core_count,
        "repair_attempts": 456,
        "final_builds_passed": builds,
        "detector_metrics_resolved": resolved,
        "private_layer3": {
            "evaluated": len(private),
            "passed": private_passes,
            "regressions": len(regressions),
            "not_run": 0,
            "oracle_manifest_version": "1.0.0",
            "regression_independent_instances": len(regression_instances),
        },
        "strict_successes": strict,
        "factorial_arms": 8,
        "attempts_per_arm": 57,
        "chapter5_4": {
            "quality_remeasurements": len(quality_rows),
            "quality_analyzer_build_failures": 0,
            "quality_ca_unavailable": 0,
            "package_counts": expected_package_counts,
        },
        "paired_primary": {
            "visible_test_risk_difference": float(primary["estimate"]),
            "ci95_lo": float(primary["ci95_lo"]),
            "ci95_hi": float(primary["ci95_hi"]),
            "exact_signflip_p": float(primary["exact_signflip_p"]),
        },
        "resources": resources,
        "codebase_archive": repair_audit["codebase_archive"],
        "glmm": {
            "seed": glmm_meta["analysis_seed"],
            "regularized_map_converged": True,
            "regularized_vb_converged": True,
            "weak_prior_converged": glmm_meta["weak_prior_diagnostic"]["optimizer"]["success"],
            "interpretation": "sensitivity evidence; paired risk differences primary",
        },
        "credential_shaped_value_scan": {"pass": True, "matching_files": []},
        "excluded_from_final_results": [
            "results/archive/glmm-analysis-unseeded-initialization"
        ],
    }
    write_json(experiment / "FINAL_EXPERIMENT_AUDIT.json", audit)

    final_ledger = experiment / "FINAL_RESULTS_SHA256SUMS.txt"
    included = [
        private_path,
        experiment / "EXPERIMENT_REPORT.md",
        experiment / "DEVIATIONS.md",
        experiment / "FINAL_EXPERIMENT_AUDIT.json",
        repo / "analysis/factorial_test_feedback_analysis.py",
        repo / "analysis/factorial_glmm.py",
        repo / "analysis/factorial_effect_figure.cjs",
        repo / "analysis/sol_thesis_figures.py",
        repo / "analysis/chapter54_quality_rescore.py",
        repo / "analysis/chapter54_sol_package.py",
        repo / "src/HybridLens.CLI/Commands/Chapter54MetricExportCommand.cs",
        repo / "src/HybridLens.CLI/Program.cs",
        experiment / "preflight/finalize_post_repair.py",
        script,
    ]
    included.extend(
        p for p in sorted(results.rglob("*"))
        if p.is_file() and "archive" not in p.parts
    )
    unique = sorted(set(included))
    final_ledger.write_text(
        "".join(f"{sha256(path)}  {path.relative_to(repo).as_posix()}\n" for path in unique),
        encoding="utf-8",
    )

    freeze = {
        "status": "final_experiment_frozen",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "campaign_id": repair_audit["campaign_id"],
        "pre_run_freeze_ledger_sha256": sha256(experiment / "PRE_RUN_SHA256SUMS.txt"),
        "post_repair_freeze_ledger_sha256": sha256(
            experiment / "POST_REPAIR_FREEZE_SHA256SUMS.txt"
        ),
        "final_results_file_count": len(unique),
        "final_results_ledger_sha256": sha256(final_ledger),
        "final_audit_sha256": sha256(experiment / "FINAL_EXPERIMENT_AUDIT.json"),
        "report_sha256": sha256(experiment / "EXPERIMENT_REPORT.md"),
        "deviations_sha256": sha256(experiment / "DEVIATIONS.md"),
    }
    write_json(experiment / "FINAL_EXPERIMENT_FREEZE.json", freeze)

    freeze_files = [
        experiment / "factorial-manifest.json",
        experiment / "PRE_RUN_SHA256SUMS.txt",
        experiment / "POST_REPAIR_FREEZE_SHA256SUMS.txt",
        final_ledger,
        experiment / "FINAL_EXPERIMENT_AUDIT.json",
        experiment / "FINAL_EXPERIMENT_FREEZE.json",
        experiment / "EXPERIMENT_REPORT.md",
        experiment / "DEVIATIONS.md",
    ]
    freeze_ledger = experiment / "FINAL_EXPERIMENT_FREEZE_SHA256SUMS.txt"
    freeze_ledger.write_text(
        "".join(
            f"{sha256(path)}  {path.relative_to(experiment).as_posix()}\n"
            for path in freeze_files
        ),
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "pass",
        "strict_successes": strict,
        "private_passes": private_passes,
        "private_regressions": len(regressions),
        "combined_nominal_cost_usd": resources["combined_nominal_cost_usd"],
        "final_results_files": len(unique),
        "freeze_ledger_sha256": sha256(freeze_ledger),
    }))


if __name__ == "__main__":
    main()
