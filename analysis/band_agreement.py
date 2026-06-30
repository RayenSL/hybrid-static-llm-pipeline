#!/usr/bin/env python3
"""
Band-agreement check (thesis "same code" reliability point; the "report agreement between both"
decision). Confirms the real HybridLens detector and the corpus-side HybridLensMeasure tool compute
the same metric values for every seeded instance, by comparing an **analyser-only run trace** against
the corpus ground-truth records' `measured_metrics`.

Usage:
    python band_agreement.py --runs "runs/*.jsonl" \
        --ground-truth ../hybrid-pipeline-corpus/ground-truth \
        --output band_agreement.csv
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
from pathlib import Path

GC_KEYS = [("ATFD", "atfd"), ("WMC", "wmc"), ("TCC", "tcc")]   # (HybridLens key, corpus key)
LM_KEYS = [("CyclomaticComplexity", "cyclomatic_complexity"), ("LinesOfCode", "lines_of_code")]
TCC_EPS = 0.01

_TYPES = {
    "godclass": "GodClass", "longmethod": "LongMethod",
    "obsoleteapiusage": "ObsoleteApiUsage", "obsoleteapi": "ObsoleteApiUsage",
}


def _norm_type(s: str | None) -> str | None:
    t = (s or "").replace(" ", "").replace("_", "").replace("-", "").lower()
    return _TYPES.get(t)


def _simple(sym: str | None) -> str:
    if not sym:
        return ""
    s = sym.strip()
    if "→" in s:                       # Obsolete-API: keep the deprecated callee (right of arrow)
        s = s.split("→", 1)[1].strip()
    if "(" in s:
        s = s.split("(", 1)[0]
    if "." in s:
        s = s.rsplit(".", 1)[1]
    return s.strip().lower()


def load_findings(pattern: str) -> list[dict]:
    paths = sorted(glob.glob(pattern)) or ([pattern] if Path(pattern).exists() else [])
    rows: list[dict] = []
    for p in paths:
        for ln in open(p, encoding="utf-8-sig"):
            ln = ln.strip()
            if ln:
                rows.append(json.loads(ln))
    return rows


def load_truth(gt_dir: str) -> list[dict]:
    return [json.load(open(p, encoding="utf-8"))
            for p in sorted(glob.glob(str(Path(gt_dir) / "records" / "*.json")))]


def match(rec: dict, findings: list[dict]) -> dict | None:
    typ = rec["anti_pattern"]
    loc = rec["location"]
    fnorm = loc["file"].replace("\\", "/").lower()
    for f in findings:
        if _norm_type(f.get("anti_pattern_type")) != typ:
            continue
        fp = (f.get("file_path") or "").replace("\\", "/").lower()
        if not fp.endswith(fnorm):
            continue
        if loc["line_start"] <= f.get("line", 0) <= loc["line_end"]:
            return f
        a, b = _simple(f.get("symbol_name")), _simple(loc.get("symbol"))
        if a and b and (a in b or b in a):
            return f
    return None


def compare(rec: dict, f: dict) -> tuple[bool, str]:
    typ = rec["anti_pattern"]
    corpus = rec.get("measured_metrics") or {}
    hl = f.get("metrics") or {}

    if typ == "ObsoleteApiUsage":
        # Binary marker: HybridLens flagged it (the finding exists) and the corpus recorded it present.
        agree = bool(corpus.get("obsolete_marker_present", True))
        return agree, "marker present (both)" if agree else "marker mismatch"

    keys = GC_KEYS if typ == "GodClass" else LM_KEYS
    diffs = []
    for hk, ck in keys:
        hv, cv = hl.get(hk), corpus.get(ck)
        if hv is None or cv is None:
            diffs.append(f"{hk}: HL={hv} corpus={cv}")
        elif hk == "TCC":
            if abs(float(hv) - float(cv)) > TCC_EPS:
                diffs.append(f"TCC: HL={hv} corpus={cv}")
        elif int(round(float(hv))) != int(round(float(cv))):
            diffs.append(f"{hk}: HL={hv} corpus={cv}")
    return (not diffs), ("exact" if not diffs else "; ".join(diffs))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="HybridLens vs HybridLensMeasure band-agreement on seeded instances.")
    ap.add_argument("--runs", required=True, help="analyser-only run trace JSONL (path or glob)")
    ap.add_argument("--ground-truth", required=True, help="corpus ground-truth dir (contains records/)")
    ap.add_argument("--output", default="band_agreement.csv")
    a = ap.parse_args(argv)

    findings = load_findings(a.runs)
    truth = load_truth(a.ground_truth)

    rows, n_match, n_agree = [], 0, 0
    for rec in truth:
        f = match(rec, findings)
        if f is None:
            rows.append({"instance_id": rec["instance_id"], "type": rec["anti_pattern"],
                         "matched": False, "agree": False, "detail": "no HybridLens finding matched"})
            continue
        n_match += 1
        agree, detail = compare(rec, f)
        n_agree += int(agree)
        rows.append({"instance_id": rec["instance_id"], "type": rec["anti_pattern"],
                     "matched": True, "agree": agree, "detail": detail})

    with open(a.output, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["instance_id", "type", "matched", "agree", "detail"])
        w.writeheader()
        w.writerows(rows)

    print(f"instances: {len(truth)} | matched by HybridLens: {n_match} | metric-agree: {n_agree}")
    for r in rows:
        if not r["agree"]:
            print(f"  DISAGREE {r['instance_id']} ({r['type']}): {r['detail']}")
    print(f"wrote {a.output}")
    return 0 if n_agree == len(truth) else 1


if __name__ == "__main__":
    raise SystemExit(main())
