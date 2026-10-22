"""Export anonymous thesis aggregates from archived reports; never runs models.

Usage: python3 check_evidence.py --private-root /path/to/reaccrual
Only allowlisted report fields are exported. Industrial identifiers, source,
commit messages, diffs and per-unit review notes are never copied.
"""
import argparse
import ast
import collections
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()
                if k not in {"excluded", "per_target", "target_id", "targets"}}
    if isinstance(value, list):
        return [clean(x) for x in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    specs = {
        "industrial_replay": ("replay/validation-1-report.json", ["confirmatory", "secondary"]),
        "industrial_recurrence": ("replay/validation-1-p1.json", ["crude"]),
        "corpus_replay": ("stratum-b-runs/validation-b1-report.json", ["H2_replication"]),
        "corpus_introductions": ("stratum-b-runs/validation-b1-introduced.json", ["R_minus_O_new_findings", "targets_with_new"]),
        "gpt": ("v04-runs/validation-v04-report.json", ["confirmatory", "secondary", "threshold_gaming", "sensitivity"]),
        "opus": ("v06-runs/validation-v06-opus-report.json", ["confirmatory", "secondary", "threshold_gaming", "sensitivity"]),
        "shadow": ("v05/analysis/report.json", ["primary_oracle_units", "static_only_units", "all_eligible", "gate_flow", "sensitivity", "gaming_checks", "cost", "persistence_in_the_developers_own_history"]),
    }
    result = {"schema": "thesis-aggregate-check/1", "sources": {}, "results": {}, "checks": []}
    for label, (rel, keys) in specs.items():
        path = args.private_root / rel
        report = read(path)
        result["sources"][label] = {"relative_report": rel, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        # Keep numeric counts called 'targets'; discard lists and all per-target rows.
        selected = {k: report[k] for k in keys}
        result["results"][label] = clean(selected)
        if label == "corpus_replay":
            result["results"][label]["recurrence"] = report["P1"]["crude"]
            result["results"][label]["independent_targets"] = len(report["per_target"])
            result["results"][label]["completed_steps"] = sum(sum(x["completed"].values()) for x in report["per_target"].values())
        if label in {"gpt", "opus"}:
            s = report["secondary"]
            cost = s["tokens_per_completed_step"]
            result["results"][label]["derived"] = {
                "loop_token_increase_percent": 100 * (cost["R-L"] / cost["R-N"] - 1),
                "completed_steps": {a: sum(x["completed"][a] for x in report["targets"]) for a in cost},
                "assigned_steps_per_arm": 4 * len(report["targets"]),
                "quality_tokens_per_completed_loop_step": s["loop"]["quality_tokens"] / sum(x["completed"]["R-L"] for x in report["targets"]),
            }
            r = s["replication"]["N_RN_minus_ON"]
            result["checks"].append({"model": label, "comparison": "R-N minus O-N new findings",
                                      "implemented_margin": r["sesoi"], "ci90": r["ci90"],
                                      "equivalent_at_margin_0_5": -.5 < r["ci90"][0] and r["ci90"][1] < .5})
            # Public constructed-corpus identifiers only; useful for reproducing plots.
            result["results"][label]["corpus_plot_data"] = [
                {k: x[k] for k in ["target_id", "type", "H3", "H4", "new_findings", "completed"]}
                for x in report["targets"]]
    reviews = read(args.private_root / "v05/analysis/review/review-decisions.json")
    result["results"]["shadow"]["review_status"] = {
        "units": len(reviews), "recorded_judgements": sum(bool(x.get("judgement")) for x in reviews.values())}
    acquisition = read(args.private_root / "replay/acquisition-2/acquisition.json")
    result["results"]["industrial_acquisition"] = {"assessed": len(acquisition), "accepted": sum(x["accepted_run"] is not None for x in acquisition)}
    feasible = [x for x in args.private_root.iterdir() if x.is_dir() and (x / "audit-summary.json").exists()]
    if len(feasible) != 1:
        raise ValueError("Expected one feasibility directory; cannot choose a frame silently")
    history = read(feasible[0] / "introductions/summary.json")
    ordinary = history["ordinary_le_10"]
    result["results"]["industrial_history"] = {
        "production_commits": history["all_commits"]["commits_with_production_changes"],
        "ordinary_commits": ordinary["commits_scanned"],
        "introductions": {k: ordinary["long_method"][k] for k in ["raw", "genuine", "genuine_commits", "still_long_at_head"]},
        "context_frame": {k: read(feasible[0] / "shadow-frame/frame.json")["funnel"][k] for k in ["within_context_bound", "oversize"]},
        "oracle_funnel": read(feasible[0] / "oracle-full-v2/funnel.json"),
    }
    for name, path in [("industrial_history", feasible[0] / "introductions/summary.json"),
                       ("context_frame", feasible[0] / "shadow-frame/frame.json"),
                       ("oracle_funnel", feasible[0] / "oracle-full-v2/funnel.json"),
                       ("industrial_acquisition", args.private_root / "replay/acquisition-2/acquisition.json")]:
        result["sources"][name] = {"archive": "private; location omitted", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    original = REPO / "experiments/confirmatory-v2-gpt56-sol-20260812"
    stats = read(original / "STATISTICAL_ANALYSIS_AUDIT.json")
    result["results"]["original"] = {"population": stats["analysis_population"], "principal_results": stats["principal_results"]}
    ledger = read(REPO / "analysis/maintenance_efficiency/budget-ledger.json")
    result["results"]["ledger"] = {k: ledger[k] for k in ["authorised_ceiling", "cumulative_recorded_tokens", "remaining"] if k in ledger}
    # Limited archived-record audit: records are not independent assignments.
    records = []
    paths = [original / "baseline.jsonl", *sorted((original / "campaign/traces").glob("*.jsonl"))]
    for path in paths:
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            d = json.loads(line)
            if "verified_repair_ladder" in d:
                records.append(d)
    unresolved = [d for d in records if d["verified_repair_ladder"] == "builds_unresolved"]
    gc03 = [d for d in records if "ReturnsHandler.cs" in d.get("file_path", "")]
    lm13 = [d for d in unresolved if "AccessDecisionEngine.cs" in d.get("file_path", "")]
    result["results"]["measurement_record_audit"] = {
        "scope": "baseline plus campaign/traces; includes intermediate snapshots and records without a repair verdict",
        "records": len(records), "unresolved_records": len(unresolved),
        "LM13_unresolved_records": len(lm13),
        "LM13_all_visible_test_records": all(d.get("visible_tests_enabled") for d in lm13),
        "GC03_records": len(gc03),
        "GC03_resolved_records": sum(d["verified_repair_ladder"] == "resolved" for d in gc03),
        "boundary": "Counts reproduce archived verdicts only. They do not independently establish helper relocation, baseline non-detection or corrected success rates."
    }
    out = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Extract the prompt as data, without importing runners or loading credentials.
    module = ast.parse((REPO / "analysis/maintenance_efficiency/reaccrual/replay_run.py").read_text(encoding="utf-8-sig"))
    neutral = next(ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "SYSTEM" for t in n.targets))
    (out.parent / "neutral_prompt.txt").write_text(neutral + "\n", encoding="utf-8")
    assert result["results"]["original"]["population"]["strict_successes"] == 586
    assert result["results"]["gpt"]["secondary"]["new_findings_per_arm"]["R-L"]["targets_with_new"] == 0
    assert result["results"]["opus"]["secondary"]["new_findings_per_arm"]["R-L"]["targets_with_new"] == 3
    assert result["results"]["shadow"]["primary_oracle_units"]["n"] == 32
    assert result["results"]["shadow"]["static_only_units"]["n"] == 3
    print("Wrote anonymous aggregate evidence and exact neutral prompt.")
    print(json.dumps({"checks": result["checks"], "review": result["results"]["shadow"]["review_status"],
                      "record_audit": result["results"]["measurement_record_audit"]}, indent=2))


if __name__ == "__main__":
    main()
