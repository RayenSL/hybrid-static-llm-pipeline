"""Trace annual detector findings through changing production files.

Only Python's standard library is required. Inputs are sealed outputs of the
multi-language campaign and the Odoo calendar correction; no Git network
access or application build is needed.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import re
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "analysis/multilanguage_evolution/results/three-rule-evidence.tar.gz"
CORRECTION = ROOT / "analysis/maintenance_associations/results/calendar-frontier-v0.2"
REPOSITORIES = ("odoo__odoo", "jenkinsci__jenkins", "apache__tomcat")
RULES = ("LongMethod", "GodClass", "ObsoleteApiUsage")
YEARS = range(2007, 2026)
CORRECTED_ODOO = {2018, 2019, 2020, 2023, 2024}
PATTERN = re.compile(r"^raw/(odoo__odoo|jenkinsci__jenkins|apache__tomcat)-(20\d\d)\.(syntax|three-rules)\.json$")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def key(record: dict) -> tuple[str, str]:
    return record["path"], record["symbol"]


def compress(kind: str, data: dict) -> dict:
    if kind == "syntax":
        return {"commit": data["commit"], "definitions": collections.Counter(key(d) for d in data["definitions"])}
    return {
        "commit": data["commit"],
        "inventory": {row["path"]: row["sha256"] for row in data["inventory"]},
        "rules": {rule["rule"]: {"status": rule["status"], "findings": rule["findings"]} for rule in data["rules"]},
        "classes": collections.defaultdict(list, _group_classes(data["class_metrics"])),
    }


def _group_classes(rows: list[dict]) -> dict:
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[key(row)].append(row["assessment"])
    return dict(grouped)


def read_inputs() -> tuple[dict, dict]:
    scans: dict = {}
    input_hashes = {"bundle": sha(BUNDLE.read_bytes()), "corrections": {}}
    with tarfile.open(BUNDLE, "r:gz") as archive:
        for member in archive:
            match = PATTERN.fullmatch(member.name)
            if not match or not member.isfile():
                continue
            repo, year, kind = match.group(1), int(match.group(2)), match.group(3)
            if year not in YEARS:
                continue
            if repo == "odoo__odoo" and year in CORRECTED_ODOO:
                continue
            raw = archive.extractfile(member).read()
            scans.setdefault((repo, year), {})[kind] = compress(kind, json.loads(raw))
    for year in sorted(CORRECTED_ODOO):
        for kind in ("syntax", "three-rules"):
            path = CORRECTION / f"odoo__odoo-{year}.{kind}.json"
            raw = path.read_bytes()
            input_hashes["corrections"][str(path.relative_to(ROOT))] = sha(raw)
            scans.setdefault(("odoo__odoo", year), {})[kind] = compress(kind, json.loads(raw))
    for repo in REPOSITORIES:
        for year in YEARS:
            item = scans.get((repo, year))
            if item is None or set(item) != {"syntax", "three-rules"}:
                raise ValueError(f"Missing paired scan: {repo} {year}")
            if item["syntax"]["commit"] != item["three-rules"]["commit"]:
                raise ValueError(f"Mismatched commit: {repo} {year}")
            for rule in RULES:
                if rule not in item["three-rules"]["rules"]:
                    raise ValueError(f"Missing rule: {repo} {year} {rule}")
    return scans, input_hashes


def classify(base: dict, nxt: dict, rule: str, finding: dict, base_counts: collections.Counter,
             next_counts: collections.Counter) -> tuple[str, str]:
    identity = key(finding)
    if base_counts[identity] != 1 or next_counts[identity] > 1:
        return "ambiguous_identity", "unknown"
    before_files = base["three-rules"]["inventory"]
    after_files = nxt["three-rules"]["inventory"]
    path = identity[0]
    if path not in before_files:
        raise ValueError(f"Finding missing from baseline inventory: {path}")
    if path not in after_files:
        return "path_absent", "unknown"
    changed = "yes" if before_files[path] != after_files[path] else "no"
    if next_counts[identity] == 1:
        return "redetected", changed
    if rule == "ObsoleteApiUsage":
        return "not_redetected", changed
    if rule == "LongMethod":
        count = nxt["syntax"]["definitions"][identity]
        if count == 1:
            return "rule_no_longer_triggered", changed
        return ("entity_absent" if count == 0 else "ambiguous_entity"), changed
    assessments = nxt["three-rules"]["classes"].get(identity, [])
    if len(assessments) == 1:
        return ("rule_no_longer_triggered" if assessments[0] == "resolved" else "entity_unassessed"), changed
    return ("entity_absent" if not assessments else "ambiguous_entity"), changed


def analyse(scans: dict) -> tuple[list[dict], list[dict], list[dict]]:
    rows = []
    intervals = []
    skipped = []
    for repo in REPOSITORIES:
        for year in range(2007, 2025):
            base, nxt = scans[(repo, year)], scans[(repo, year + 1)]
            for rule in RULES:
                br, nr = base["three-rules"]["rules"][rule], nxt["three-rules"]["rules"][rule]
                if br["status"] != "complete" or nr["status"] != "complete":
                    skipped.append({"repository": repo, "baseline_year": year, "next_year": year + 1,
                                    "rule": rule, "baseline_status": br["status"], "next_status": nr["status"]})
                    continue
                bc = collections.Counter(key(f) for f in br["findings"])
                nc = collections.Counter(key(f) for f in nr["findings"])
                counts = collections.Counter()
                for finding in br["findings"]:
                    state, changed = classify(base, nxt, rule, finding, bc, nc)
                    counts[(changed, state)] += 1
                    rows.append({"repository": repo, "baseline_year": year, "next_year": year + 1,
                                 "baseline_commit": base["three-rules"]["commit"],
                                 "next_commit": nxt["three-rules"]["commit"], "rule": rule,
                                 "path": finding["path"], "symbol": finding["symbol"],
                                 "finding_id": finding["id"], "file_changed": changed, "state": state})
                if sum(counts.values()) != len(br["findings"]):
                    raise ValueError(f"Transition count mismatch: {repo} {year} {rule}")
                intervals.append({"repository": repo, "baseline_year": year, "next_year": year + 1,
                                  "rule": rule, "baseline_findings": len(br["findings"]),
                                  **{f"{change}_{state}": value for (change, state), value in sorted(counts.items())}})
    return rows, intervals, skipped


def summary(rows: list[dict], intervals: list[dict], skipped: list[dict]) -> list[dict]:
    output = []
    for repo in REPOSITORIES:
        for rule in RULES:
            r = [x for x in rows if x["repository"] == repo and x["rule"] == rule]
            counts = collections.Counter((x["file_changed"], x["state"]) for x in r)
            changed_total = sum(v for (c, _), v in counts.items() if c == "yes")
            unchanged_total = sum(v for (c, _), v in counts.items() if c == "no")
            changed_redetected = counts[("yes", "redetected")]
            changed_entity_present = changed_redetected + counts[("yes", "rule_no_longer_triggered")]
            output.append({
                "repository": repo, "rule": rule,
                "complete_intervals": sum(x["repository"] == repo and x["rule"] == rule for x in intervals),
                "skipped_intervals": sum(x["repository"] == repo and x["rule"] == rule for x in skipped),
                "baseline_finding_observations": len(r),
                "changed_file_findings": changed_total,
                "changed_file_redetected": changed_redetected,
                "changed_file_redetection_share": round(changed_redetected / changed_total, 6) if changed_total else None,
                "changed_file_structural_entity_observable": changed_entity_present if rule != "ObsoleteApiUsage" else None,
                "changed_file_structural_entity_retention_share": round(changed_redetected / changed_entity_present, 6) if changed_entity_present and rule != "ObsoleteApiUsage" else None,
                "changed_file_rule_no_longer_triggered": counts[("yes", "rule_no_longer_triggered")],
                "changed_file_not_redetected": counts[("yes", "not_redetected")],
                "changed_file_entity_absent": counts[("yes", "entity_absent")],
                "changed_file_entity_unassessed": counts[("yes", "entity_unassessed")],
                "changed_file_ambiguous_entity": counts[("yes", "ambiguous_entity")],
                "unchanged_file_findings": unchanged_total,
                "unchanged_file_redetected": counts[("no", "redetected")],
                "unchanged_file_nonredetected": unchanged_total - counts[("no", "redetected")],
                "path_absent": counts[("unknown", "path_absent")],
                "ambiguous_identity": counts[("unknown", "ambiguous_identity")],
            })
    return output



def observed_runs(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    groups = collections.defaultdict(list)
    for row in rows:
        if row["state"] == "redetected":
            groups[(row["repository"], row["rule"], row["path"], row["symbol"])].append(row)
    episodes = []
    for identity, edges in sorted(groups.items()):
        edges.sort(key=lambda row: row["baseline_year"])
        current = []
        for edge in edges:
            if current and edge["baseline_year"] != current[-1]["next_year"]:
                episodes.append(_run_record(identity, current))
                current = []
            current.append(edge)
        if current:
            episodes.append(_run_record(identity, current))
    counts = []
    for repo in REPOSITORIES:
        for rule in RULES:
            subset = [row for row in episodes if row["repository"] == repo and row["rule"] == rule]
            long = [row for row in subset if row["observed_scans"] >= 3]
            counts.append({"repository": repo, "rule": rule, "redetected_runs": len(subset),
                           "runs_at_least_three_scans": len(long),
                           "long_runs_with_file_change": sum(row["changed_file_intervals"] > 0 for row in long),
                           "maximum_observed_scans": max((row["observed_scans"] for row in subset), default=0)})
    return episodes, counts


def _run_record(identity: tuple, edges: list[dict]) -> dict:
    repo, rule, path, symbol = identity
    return {"repository": repo, "rule": rule, "path": path, "symbol": symbol,
            "first_year": edges[0]["baseline_year"], "last_year": edges[-1]["next_year"],
            "observed_scans": len(edges) + 1,
            "changed_file_intervals": sum(row["file_changed"] == "yes" for row in edges),
            "unchanged_file_intervals": sum(row["file_changed"] == "no" for row in edges)}


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "analysis/active_persistence/results/v1.0")
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"Refusing to overwrite populated output: {out}")
    out.mkdir(parents=True, exist_ok=True)
    scans, input_hashes = read_inputs()
    transitions, intervals, skipped = analyse(scans)
    summaries = summary(transitions, intervals, skipped)
    episodes, episode_summaries = observed_runs(transitions)
    write_csv(out / "finding-transitions.csv", transitions)
    interval_fields = ["repository", "baseline_year", "next_year", "rule", "baseline_findings"]
    interval_fields += sorted(set().union(*(set(row) for row in intervals)) - set(interval_fields))
    write_csv(out / "intervals.csv", intervals, interval_fields)
    write_csv(out / "skipped-intervals.csv", skipped,
              ["repository", "baseline_year", "next_year", "rule", "baseline_status", "next_status"])
    write_csv(out / "summary.csv", summaries)
    write_csv(out / "observed-runs.csv", episodes)
    write_csv(out / "run-summary.csv", episode_summaries)
    (out / "summary.json").write_bytes(canonical(summaries))
    provenance = {"protocol": "v1.0", "inputs": input_hashes, "script_sha256": sha(Path(__file__).read_bytes()),
                  "transition_rows": len(transitions), "complete_rule_intervals": len(intervals),
                  "skipped_rule_intervals": len(skipped), "observed_runs": len(episodes)}
    (out / "provenance.json").write_bytes(canonical(provenance))
    seals = {path.name: sha(path.read_bytes()) for path in sorted(out.iterdir()) if path.is_file()}
    (out / "SHA256SUMS.json").write_bytes(canonical(seals))
    print(json.dumps({"output": str(out), **{k: provenance[k] for k in
          ("transition_rows", "complete_rule_intervals", "skipped_rule_intervals")}}, sort_keys=True))


if __name__ == "__main__":
    main()
