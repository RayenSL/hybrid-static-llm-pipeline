#!/usr/bin/env python3
"""Analyze the sealed four-level direct-edit context-ladder campaign."""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import warnings
from collections import Counter, defaultdict
from pathlib import Path

try:
    from analysis.matched_statistics import cochran_q, exact_mcnemar, holm_adjust
except ModuleNotFoundError:  # Direct execution: python analysis/context_ladder_analysis.py
    from matched_statistics import cochran_q, exact_mcnemar, holm_adjust

LEVELS = ["minimal", "structural", "relational", "full"]
SUCCESSOR_TARGETS = {"EmailClient", "LabelPrinter", "ReminderSender", "SmsClient"}
OLD_API = {
    "CalendarFeed": "FeedApiV1", "CurrencyConverter": "RatesV1",
    "EmailClient": "MailApiV1", "LabelPrinter": "LabelApiV1",
    "PdfExporter": "RenderApiV1", "PushClient": "PushApiV1",
    "ReminderSender": "NotifyApiV1", "SmsClient": "SmsApiV1",
    "SnapshotWriter": "SnapshotApiV1", "StockSync": "SyncApiV1",
}
MIGRATION_MARKERS = re.compile(
    r"(?:ApiV2|IRateProvider|ICalendarWriter|IDocumentWriter|IPushProvider|"
    r"IInventoryStore|IStockLedger|TableRateProvider|SimpleDocumentWriter|ICalWriter|"
    r"DefaultPushProvider|InMemoryInventoryStore|InMemoryStockLedger)\b"
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line]


def validate_model_ready_data(data) -> tuple[int, int]:
    observations = len(data)
    instances = int(data["instance_id"].nunique())
    counts = data.groupby("instance_id").size()
    level_counts = data.groupby(["instance_id", "context_level"]).size()
    if (instances < 2 or observations != instances * 12 or not (counts == 12).all()
            or set(data["context_level"]) != set(LEVELS) or not (level_counts == 3).all()):
        raise ValueError("model-ready data must contain 12 context-ladder attempts "
                         "(4 levels x 3 repetitions) for every independent instance")
    return observations, instances


def grade_obsolete_resolution(source: str, obsolete_type: str) -> str:
    if re.search(rf"\b{re.escape(obsolete_type)}\b", source):
        return "evaded"
    if MIGRATION_MARKERS.search(source):
        return "migrated"
    if obsolete_type == "SyncApiV1" and re.search(r"countedQuantity\s*-\s*item\.OnHand", source):
        return "evaded"
    return "ambiguous"


def metric_delta(row: dict, before: str, after: str):
    if row.get(before) is None or row.get(after) is None:
        return None
    return row[after] - row[before]


def successor_subset(rows: list[dict]) -> list[dict]:
    result = []
    for level in ("relational", "full"):
        selected = [x for x in rows if x["target"] in SUCCESSOR_TARGETS and x["context_level"] == level]
        result.append({"level": level, "resolved": sum(int(x["verified"]) for x in selected),
                       "migrated": sum(x.get("obsolete_grade") == "migrated" for x in selected),
                       "n": len(selected)})
    return result


def behavior_preserving_count(rows: list[dict]) -> int:
    return sum(bool(x["verified"]) and x["layer3_passed"] is True for x in rows)


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def fit_glmm(data, out: Path) -> dict:
    import numpy as np
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
    formula = "verified ~ C(context_level, Treatment('minimal')) + C(anti_pattern_type)"
    vc = {"instance": "0 + C(instance_id)"}
    np.random.seed(1819459010)
    model = BinomialBayesMixedGLM.from_formula(formula, vc, data, vcp_p=.5, fe_p=2)
    result = model.fit_map()
    np.random.seed(1819459010)
    vb_model = BinomialBayesMixedGLM.from_formula(formula, vc, data, vcp_p=.5, fe_p=2)
    vb = vb_model.fit_vb()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        weak = BinomialBayesMixedGLM.from_formula(formula, vc, data, vcp_p=1, fe_p=10).fit_map()
    rows = []
    for estimator, fitted, names in (("laplace_map", result, model.exog_names),
                                      ("variational_bayes", vb, vb_model.exog_names)):
        for name, mean, sd in zip(names, fitted.fe_mean, fitted.fe_sd):
            rows.append({"estimator": estimator, "term": name, "log_odds": float(mean),
                         "approx_sd": float(sd), "odds_ratio": math.exp(float(mean))})
    write_csv(out / "glmm_fixed_effects.csv", rows)
    return {
        "formula": formula + " + (1 | instance_id)",
        "map_optimizer": {"success": bool(getattr(result.optim_retvals, "success", False)),
                          "message": str(getattr(result.optim_retvals, "message", "")),
                          "max_abs_gradient": float(max(abs(x) for x in result.optim_retvals.jac))},
        "map_random_intercept_sd": math.exp(float(result.vcp_mean[0])),
        "vb_random_intercept_sd": math.exp(float(vb.vcp_mean[0])),
        "weak_prior": {"success": bool(getattr(weak.optim_retvals, "success", False)),
                       "warnings": [str(x.message) for x in caught],
                       "random_intercept_sd": math.exp(float(weak.vcp_mean[0]))},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(); exp = args.experiment; out = args.out
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((exp / "ladder-manifest.json").read_text(encoding="utf-8-sig"))
    ledger = {x["assignment_id"]: x for x in read_jsonl(exp / "campaign/execution-ledger.jsonl")}
    layer3 = {x["artifact_id"]: x for x in read_jsonl(exp / "private-results/layer3.jsonl")}
    quality = {x["artifact_id"]: x for x in read_jsonl(exp / "quality-results/layer2.jsonl")}
    attempts = []
    for assignment in manifest["assignments"]:
        entry = ledger[assignment["assignment_id"]]
        trace = read_jsonl(Path(entry["trace_file"]))[-1]
        artifact = json.loads(Path(trace["materialized_source_ref"]).read_text(encoding="utf-8-sig"))
        aid = artifact["artifact_id"]; target = Path(assignment["file_path"]).stem
        l3 = layer3[aid]; q = quality[aid]
        verified = bool(trace["verified_repair_success"])
        grade = None
        if assignment["anti_pattern_type"] == "obsolete_api_usage" and verified:
            grade = grade_obsolete_resolution(artifact["final_source"], OLD_API[target])
        attempts.append({
            "assignment_id": assignment["assignment_id"], "block_id": assignment["block_id"],
            "instance_id": assignment["file_path"], "target": target,
            "run_number": assignment["run_number"], "context_level": assignment["context_level"],
            "anti_pattern_type": assignment["anti_pattern_type"], "verified": int(verified),
            "repair_ladder": trace["verified_repair_ladder"], "build_passed": bool(trace["build_passed"]),
            "layer3_evaluated": bool(l3["evaluated"]), "layer3_passed": l3["passed"],
            "obsolete_grade": grade, "input_tokens": int(entry["input_tokens"] or 0),
            "output_tokens": int(entry["output_tokens"] or 0),
            "prompt_characters": len(trace["raw_user_prompt"]),
            "cost_usd": (5*int(entry["input_tokens"] or 0)+30*int(entry["output_tokens"] or 0))/1e6,
            "cross_file_truncated": bool(entry["cross_file_truncated"]),
            "smell_delta": metric_delta(q,"smell_total_before","smell_total_after"),
            "ca_headline_delta": metric_delta(q,"ca_headline_before","ca_headline_after"),
            "ca_all_delta": metric_delta(q,"ca_all_before","ca_all_after"),
        })
    import pandas as pd
    data = pd.DataFrame(attempts); observations, instances = validate_model_ready_data(data)
    data.to_csv(out / "attempts.csv", index=False)

    by_block = defaultdict(dict)
    for row in attempts: by_block[row["block_id"]][row["context_level"]] = row["verified"]
    matrix = [[by_block[b][level] for level in LEVELS] for b in sorted(by_block)]
    q_stat, q_df, q_p = cochran_q(matrix)
    contrasts = [("structural-minimal", "minimal", "structural"),
                 ("relational-structural", "structural", "relational"),
                 ("full-relational", "relational", "full")]
    pairwise = []
    for label, lo, hi in contrasts:
        a=[by_block[b][lo] for b in sorted(by_block)]; b=[by_block[x][hi] for x in sorted(by_block)]
        lo_only, hi_only, p = exact_mcnemar(a,b)
        pairwise.append({"contrast": label, "lower_only": lo_only, "higher_only": hi_only,
                         "risk_difference_pp": 100*(sum(b)-sum(a))/len(a), "p": p})
    for row, adjusted in zip(pairwise, holm_adjust([x["p"] for x in pairwise])):
        row["holm_p"] = adjusted

    levels=[]
    for level in LEVELS:
        rows=[x for x in attempts if x["context_level"]==level]; ladder=Counter(x["repair_ladder"] for x in rows)
        scored=[x for x in rows if x["smell_delta"] is not None]
        levels.append({"level":level,"n":len(rows),"build_fails":ladder["build_fails"],
            "builds_unresolved":ladder["builds_unresolved"],"resolved":sum(x["verified"] for x in rows),
            "layer3_pass":sum(x["layer3_passed"] is True for x in rows),
            "layer3_fail":sum(x["layer3_passed"] is False for x in rows),
            "detector_resolved_and_layer3_pass":behavior_preserving_count(rows),
            "quality_scored_n":len(scored),
            "smell_delta_mean":sum(x["smell_delta"] for x in scored)/len(scored) if scored else None,
            "ca_headline_delta_mean":sum(x["ca_headline_delta"] for x in scored)/len(scored) if scored else None,
            "ca_all_delta_mean":sum(x["ca_all_delta"] for x in scored)/len(scored) if scored else None,
            "prompt_characters_mean":sum(x["prompt_characters"] for x in rows)/len(rows),
            "input_tokens":sum(x["input_tokens"] for x in rows),"output_tokens":sum(x["output_tokens"] for x in rows),
            "nominal_cost_usd":sum(x["cost_usd"] for x in rows),
            "cross_file_truncated":sum(x["cross_file_truncated"] for x in rows)})
    stratified=[]
    for pattern in sorted(data.anti_pattern_type.unique()):
        for level in LEVELS:
            rows=[x for x in attempts if x["anti_pattern_type"]==pattern and x["context_level"]==level]
            stratified.append({"anti_pattern_type":pattern,"level":level,"resolved":sum(x["verified"] for x in rows),"n":len(rows)})
    grading=[]
    for row in attempts:
        if row["obsolete_grade"]:
            grading.append({k:row[k] for k in ("assignment_id","target","run_number","context_level","obsolete_grade","layer3_passed")})
    glmm = fit_glmm(data, out)
    summary={"observations":observations,"instances":instances,"matched_blocks":len(by_block),
        "cochran_q":{"statistic":q_stat,"df":q_df,"p":q_p},"adjacent_contrasts":pairwise,
        "levels":levels,"stratified":stratified,"obsolete_grading":dict(Counter(x["obsolete_grade"] for x in grading)),
        "successor_mechanism_n":4,"successor_subset":successor_subset(attempts),
        "ceiling_control_mde_pp":{"n_targets_each":13,
            "approx_two_sided_alpha_0.05_power_0.80_worst_case":100*(1.9599639845+.8416212336)/math.sqrt(13)},
        "glmm":glmm,"cost_basis":"nominal USD at $5/M input and $30/M output tokens"}
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    write_csv(out/"level_summary.csv",levels); write_csv(out/"stratified_summary.csv",stratified)
    if grading: write_csv(out/"obsolete_grading.csv",grading)
    report=["# Context-ladder corpus v2 outcomes","",f"Cochran Q={q_stat:.4f}, df={q_df}, p={q_p:.6g}.","",
            "## Levels","",dataframe_markdown(levels),"","## Adjacent contrasts","",dataframe_markdown(pairwise),"",
            "## Successor-available Obsolete API subset (n = 4 targets)","",dataframe_markdown(summary["successor_subset"]),"",
            "## Obsolete API grading","",str(summary["obsolete_grading"]),"",
            "The sharpest successor-availability mechanism claim has n = 4 targets. Detector resolution is not behaviour preservation; Obsolete API Layer 3 is a smoke oracle."]
    (out/"REPORT.md").write_text("\n".join(report)+"\n",encoding="utf-8")


def dataframe_markdown(rows: list[dict]) -> str:
    keys=list(rows[0]); lines=["| "+" | ".join(keys)+" |","|"+"|".join("---" for _ in keys)+"|"]
    lines += ["| "+" | ".join(str(r[k]) for k in keys)+" |" for r in rows]
    return "\n".join(lines)


if __name__ == "__main__": main()
