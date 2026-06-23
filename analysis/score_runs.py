"""
Interactive scoring tool — produces `experiments.jsonl` from the rated subset.

Implements the rubric defined in Appendix B of the thesis:
  - 3-point ordinal (poor / adequate / good) on 8 dimensions
  - Multi-label hallucination (8 categories, §B.6)
  - Quality-attribute alignment task (§B.7) with three counts
  - Mandatory rationale on Poor or uncertain ratings (§B.3.2)
  - Per-rating uncertain flag
  - Rater identity, rubric version, ISO timestamps, blinding-lot tag (§B.10.1)
  - Refusal auto-detection (§B.3.4)
  - Blinded HTML viewer — hides context_level, model_name, run_number,
    prompt_version (§B.2.1)
  - Pilot mode passthrough (the selection script handles --pilot)

Pipeline position:
    select_rating_set.py
        ↓
    experiments_to_rate.jsonl   (one row per cell, stratified order)
        ↓  score_runs.py --rater R1
    experiments.jsonl

For the second rater, run with `--rater R2 --output experiments_R2.jsonl` on
the IRR subset (a smaller file produced by select_rating_set.py with --pilot or
with manual subsetting); compare_raters.py then computes Cohen's weighted κ.
"""
from __future__ import annotations

import argparse
import glob as _glob
import html
import json
import re
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path


# ── Constants ────────────────────────────────────────────────────────────────

RUBRIC_VERSION = "1.0"

ORDINAL_VALUES = ("poor", "adequate", "good")

# Explanation dimensions — independent ratings per §B.4
EXPLANATION_DIMS = [
    ("explanation_correctness",   "Explanation correctness    "),
    ("explanation_groundedness",  "Explanation groundedness   "),
    ("explanation_completeness",  "Explanation completeness   "),
    ("explanation_clarity",       "Explanation clarity        "),
]

# Repair dimensions — independent ratings per §B.5.
# semantic_risk is reverse-coded: Good = low risk.
REPAIR_DIMS = [
    ("repair_correctness",        "Repair correctness         "),
    ("repair_completeness",       "Repair completeness        "),
    ("repair_actionability",      "Repair actionability       "),
    ("repair_semantic_risk",      "Repair semantic risk (rev) "),
]

ALL_DIMS = EXPLANATION_DIMS + REPAIR_DIMS

# Hallucination taxonomy (§B.6) — multi-label, with "none" as the empty-set marker.
HALLUCINATION_CATEGORIES = [
    "factual_fabrication",
    "context_inconsistency",
    "intent_mismatch",
    "incomplete_suggestion",
    "irrelevant_suggestion",
    "risky_repair",
    "over_generalisation",
]

HALLUCINATION_DESCRIPTIONS = {
    "factual_fabrication":   "Invented APIs/classes/methods, or false claims about the code or framework.",
    "context_inconsistency": "Output contradicts information explicitly supplied in the prompt.",
    "intent_mismatch":       "Addresses a different issue than the detected anti-pattern.",
    "incomplete_suggestion": "Repair is missing implementation steps that would block a developer.",
    "irrelevant_suggestion": "Technically plausible advice that does not apply to this specific finding.",
    "risky_repair":          "Repair would alter semantics or omit constraints without flagging the risk.",
    "over_generalisation":   "Explanation is generic and not grounded in the specific code.",
}

# Refusal patterns (§B.3.4) — case-insensitive; auto-pre-fills the row as Poor.
REFUSAL_PATTERNS = [
    r"\bI\s+cannot\s+(help|assist|provide)",
    r"\bI\s+(?:am|'m)\s+unable\s+to",
    r"\bI\s+(?:won't|will not)\s+(?:help|assist|provide)",
    r"\bsorry,?\s+(?:but\s+)?I\s+(?:cannot|can't|am not able)",
    r"\bI\s+do(?:\s+not|n't)\s+(?:have|provide)\s+(?:the\s+)?(?:ability|context|information)",
]
_REFUSAL_RE = re.compile("|".join(REFUSAL_PATTERNS), re.IGNORECASE)


# ── Sentinels ────────────────────────────────────────────────────────────────

class _Sentinel:
    def __init__(self, name): self.name = name
    def __repr__(self): return f"<{self.name}>"

QUIT = _Sentinel("QUIT")
SKIP = _Sentinel("SKIP")


# ── I/O ──────────────────────────────────────────────────────────────────────

def expand_inputs(patterns: list[str]) -> list[Path]:
    out: list[Path] = []
    for pat in patterns:
        matches = _glob.glob(pat)
        if matches:
            out.extend(Path(m) for m in matches)
        elif Path(pat).exists():
            out.append(Path(pat))
    return sorted(set(out))


def read_jsonl(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for p in paths:
        with p.open("r", encoding="utf-8-sig") as fh:
            for line_no, raw in enumerate(fh, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rows.append(json.loads(raw))
                except json.JSONDecodeError as ex:
                    print(f"  [warn] {p}:{line_no} skipped — {ex}", file=sys.stderr)
    return rows


def read_already_scored(output_path: Path, rater_id: str) -> set[str]:
    """Resume support: skip run_ids already scored by THIS rater."""
    if not output_path.exists():
        return set()
    seen: set[str] = set()
    with output_path.open("r", encoding="utf-8-sig") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
                if row.get("rater_id") == rater_id and "run_id" in row:
                    seen.add(row["run_id"])
            except json.JSONDecodeError:
                continue
    return seen


def append_record(output_path: Path, record: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False))
        fh.write("\n")


# ── Pre-processing ───────────────────────────────────────────────────────────

def detect_refusal(text: str | None) -> bool:
    if not text:
        return False
    return bool(_REFUSAL_RE.search(text))


def auto_refusal_record(run: dict) -> dict:
    """Build a Poor-everywhere record with rationale 'refusal' (§B.3.4)."""
    rec: dict = {}
    for field, _ in ALL_DIMS:
        rec[field]                   = "poor"
        rec[f"{field}_rationale"]    = "refusal"
        rec[f"{field}_uncertain"]    = False
    rec["hallucination_categories"] = []   # refusal is not a hallucination per se
    rec["refusal_detected"]         = True
    return rec


# ── Console prompts ──────────────────────────────────────────────────────────

def _parse_ordinal(raw: str) -> str | None:
    raw = raw.strip().lower()
    if raw in ("p", "poor"):     return "poor"
    if raw in ("a", "adequate"): return "adequate"
    if raw in ("g", "good"):     return "good"
    return None


def prompt_ordinal(label: str) -> tuple[str, str | None, bool] | _Sentinel:
    """Returns (value, rationale, uncertain) or QUIT / SKIP."""
    while True:
        raw = input(f"  {label} [p/a/g, ? for uncertain, skip, quit]: ").strip().lower()
        if raw == "quit": return QUIT
        if raw == "skip": return SKIP

        uncertain = False
        if raw.endswith("?") and len(raw) > 1:
            uncertain = True
            raw = raw[:-1].strip()
        elif raw == "?":
            print("    '?' alone — please pick the closer value first, then mark uncertain (e.g. 'p?').")
            continue

        value = _parse_ordinal(raw)
        if value is None:
            print("    Expected p / a / g (optionally followed by ? for uncertain).")
            continue

        # Rationale is mandatory for Poor (§B.3.2) or any uncertain rating.
        rationale: str | None = None
        if value == "poor" or uncertain:
            rationale = input("    Rationale (mandatory): ").strip()
            if not rationale:
                print("    Rationale cannot be empty for Poor or uncertain — try again.")
                continue
        return value, rationale, uncertain


def prompt_multi_label_indices(label: str, options: list[str],
                               descriptions: dict[str, str]) -> list[str] | _Sentinel:
    """Multi-select multi-label prompt. Space-separated indices; blank or '0' = none."""
    while True:
        print(f"  {label}")
        print("    Enter space-separated indices, blank or '0' for none, skip, quit.")
        for i, opt in enumerate(options, start=1):
            desc = descriptions.get(opt, "")
            print(f"      [{i}] {opt:<24}  {desc}")
        raw = input("  > ").strip().lower()
        if raw == "quit": return QUIT
        if raw == "skip": return SKIP
        if raw == "" or raw == "0":
            return []

        try:
            indices = [int(tok) for tok in raw.split()]
        except ValueError:
            print("    Expected integers.")
            continue
        if any(i < 0 or i > len(options) for i in indices):
            print(f"    Out of range — pick from 1..{len(options)}")
            continue
        picked = [options[i - 1] for i in indices if 1 <= i <= len(options)]
        # De-duplicate while preserving order
        seen = set()
        unique = [c for c in picked if not (c in seen or seen.add(c))]
        return unique


def prompt_int(label: str, default: int, min_val: int = 0) -> int | _Sentinel:
    while True:
        raw = input(f"  {label} (default: {default}, skip, quit): ").strip().lower()
        if raw == "quit": return QUIT
        if raw == "skip": return SKIP
        if raw == "":     return default
        try:
            v = int(raw)
        except ValueError:
            print(f"    Expected an integer >= {min_val}.")
            continue
        if v < min_val:
            print(f"    Must be >= {min_val}.")
            continue
        return v


def prompt_optional(label: str) -> str | None:
    raw = input(f"  {label}: ").strip()
    return raw or None


# ── Console viewer (blinded) ─────────────────────────────────────────────────

def show_run_console(run: dict, idx: int, total: int) -> None:
    print()
    print("═" * 100)
    print(f"  [{idx}/{total}]")
    print("═" * 100)
    # Blinded display — only the instance-identifying + analyser-visible info.
    print(f"  Anti-pattern : {run.get('anti_pattern_type')}")
    print(f"  Severity     : {run.get('severity')}")
    print(f"  Location     : {run.get('file_path')}:{run.get('line')}")
    print(f"  Symbol       : {run.get('symbol_name')}")
    if run.get("error_status"):
        print(f"  ERROR        : {run.get('error_status')}  ({run.get('error_message')})")

    expl = run.get("parsed_explanation") or run.get("raw_llm_output") or ""
    qi   = run.get("parsed_quality_impact") or ""
    rep  = run.get("parsed_suggested_fix") or ""

    print()
    print("  ── Explanation " + "─" * 84)
    print(_indent(expl, 4))
    if qi:
        print()
        print("  ── Quality impact " + "─" * 81)
        print(_indent(qi, 4))
    if rep:
        print()
        print("  ── Suggested fix " + "─" * 82)
        print(_indent(rep, 4))


def _indent(text: str, spaces: int, max_lines: int = 60) -> str:
    text = (text or "").rstrip()
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"… [{len(text.splitlines()) - max_lines} more lines truncated]"]
    pad = " " * spaces
    return "\n".join(pad + ln for ln in lines)


# ── HTML viewer (blinded) ────────────────────────────────────────────────────

_HTML_CSS = """
:root {
  --bg: #f7f7f8; --fg: #1f2328; --muted: #57606a;
  --panel: #ffffff; --border: #d0d7de; --accent: #0969da;
  --code-bg: #0d1117; --code-fg: #e6edf3; --code-hl: #3a2e00;
  --chip-bg: #ddf4ff; --chip-fg: #0550ae;
  --good: #1a7f37; --bad: #cf222e; --neutral: #6e7781;
}
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 32px; font: 14px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;
       color: var(--fg); background: var(--bg); }
h1 { margin: 0 0 6px; font-size: 18px; font-weight: 600; word-break: break-all; }
h2 { margin: 18px 0 8px; font-size: 13px; text-transform: uppercase; letter-spacing: 0.04em;
     color: var(--muted); border-bottom: 1px solid var(--border); padding-bottom: 4px; }
.loc { color: var(--muted); font-family: ui-monospace,Consolas,monospace; font-size: 12px; }
.chip { display: inline-block; padding: 2px 9px; margin: 0 4px 4px 0; border-radius: 999px;
        background: var(--chip-bg); color: var(--chip-fg); font-size: 11px; font-weight: 600; }
.chip.warn { background: #fff8c5; color: #633c01; }
.chip.crit { background: #ffebe9; color: var(--bad); }
.banner { display: flex; gap: 18px; padding: 10px 14px; margin: 14px 0 18px;
          background: var(--panel); border: 1px solid var(--border); border-radius: 6px; }
.banner > div { flex: 1; }
.banner .label { font-size: 11px; text-transform: uppercase; color: var(--muted);
                 letter-spacing: 0.04em; }
.banner .val { font-family: ui-monospace,Consolas,monospace; font-size: 13px; word-break: break-word; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.panel { background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
         padding: 14px 18px; min-width: 0; }
pre { margin: 0; white-space: pre-wrap; word-break: break-word; }
pre.code { background: var(--code-bg); color: var(--code-fg); padding: 14px;
           border-radius: 6px; font: 12.5px/1.5 ui-monospace,Consolas,monospace;
           overflow-x: auto; max-height: 600px; }
pre.code .ln { display: inline-block; width: 3.5ch; color: #6e7681; user-select: none;
               text-align: right; padding-right: 1ch; border-right: 1px solid #30363d;
               margin-right: 1ch; }
pre.code .hl { background: var(--code-hl); }
.md { background: #fafbfc; border: 1px solid #eaeef2; border-radius: 4px;
      padding: 10px 14px; white-space: pre-wrap; }
.hallu-list { background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
              padding: 10px 14px; margin-top: 14px; font-size: 13px; }
.hallu-list ul { margin: 4px 0 0; padding-left: 0; list-style: none; }
.hallu-list li { padding: 4px 0; border-bottom: 1px dotted #eaeef2; }
.hallu-list li:last-child { border-bottom: none; }
.hallu-list .idx { display: inline-block; min-width: 1.5em; color: var(--accent); font-weight: 700; }
.hallu-list code { background: #eaeef2; padding: 1px 5px; border-radius: 3px; font-size: 12px; }
.empty { color: var(--muted); font-style: italic; }
.progress { color: var(--muted); font-size: 12px; }
.warn { background: #fff8c5; border: 1px solid #d4a72c; border-radius: 6px;
        padding: 8px 14px; margin: 0 0 12px; font-size: 13px; }
"""


def _html_escape(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def _code_block(snippet: str | None, finding_line: int | None) -> str:
    if not snippet:
        return '<div class="empty">no snippet</div>'
    lines = snippet.rstrip().splitlines() or [""]
    out: list[str] = []
    for i, raw in enumerate(lines):
        ln_num = (finding_line or 1) + i if finding_line and finding_line > 1 and i == 0 \
                 else 1 + i
        cls = "hl" if (finding_line and ln_num == finding_line) else ""
        out.append(
            f'<span class="{cls}"><span class="ln">{ln_num}</span>{_html_escape(raw)}</span>'
        )
    return f'<pre class="code">{"".join(out)}</pre>'


def _attr_chips(attrs) -> str:
    if not attrs: return '<span class="empty">—</span>'
    return "".join(f'<span class="chip">{_html_escape(a)}</span>' for a in attrs)


def render_run_html(run: dict, idx: int, total: int) -> str:
    sev = (run.get("severity") or "").lower()
    sev_chip_cls = "chip crit" if sev == "critical" else "chip warn" if sev == "warning" else "chip"

    # Blinded header chips: only analyser-visible information.
    head_chips = "".join([
        f'<span class="{sev_chip_cls}">{_html_escape(run.get("severity", "?"))}</span>',
        f'<span class="chip">{_html_escape(run.get("anti_pattern_type", "?"))}</span>',
    ])

    err_html = ""
    if run.get("error_status"):
        err_html = (
            f'<div class="panel" style="border-color:var(--bad);background:#fff5f5">'
            f'<strong style="color:var(--bad)">Error: {_html_escape(run.get("error_status"))}</strong>'
            f'<div class="md">{_html_escape(run.get("error_message"))}</div></div>'
        )

    refusal_html = ""
    if detect_refusal(run.get("raw_llm_output") or run.get("parsed_explanation")):
        refusal_html = (
            '<div class="warn">Refusal detected — the scorer will pre-fill all '
            'dimensions as <strong>Poor</strong> with rationale "refusal" (§B.3.4). '
            'You can override in the console.</div>'
        )

    expected = run.get("expected_quality_attributes") or []
    mentioned = run.get("llm_quality_attributes_mentioned") or []

    # Hallucination reference list (read-only display; rater enters indices in console).
    hallu_items = "".join(
        f'<li><span class="idx">[{i}]</span> '
        f'<code>{_html_escape(cat)}</code> — {_html_escape(HALLUCINATION_DESCRIPTIONS[cat])}</li>'
        for i, cat in enumerate(HALLUCINATION_CATEGORIES, start=1)
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="2">
  <title>Scoring [{idx}/{total}] — {_html_escape(run.get("symbol_name", ""))}</title>
  <style>{_HTML_CSS}</style>
</head>
<body>
  <div class="progress">Scoring run {idx} of {total} · auto-refreshes every 2 s · BLINDED VIEW</div>
  <h1>{_html_escape(run.get("symbol_name", ""))}</h1>
  <div class="loc">{_html_escape(run.get("file_path", ""))}:{run.get("line", "")}</div>
  <div style="margin-top:8px">{head_chips}</div>

  {refusal_html}

  <div class="banner">
    <div>
      <div class="label">Expected attributes (literature ground truth)</div>
      <div class="val">{_attr_chips(expected)}</div>
    </div>
    <div>
      <div class="label">Mentioned in output (auto-extracted)</div>
      <div class="val">{_attr_chips(mentioned)}</div>
    </div>
  </div>

  {err_html}

  <div class="cols">
    <div class="panel">
      <h2>Code snippet</h2>
      {_code_block(run.get("snippet") or "", run.get("line"))}
    </div>
    <div class="panel">
      <h2>Explanation</h2>
      <div class="md">{_html_escape(run.get("parsed_explanation") or "—")}</div>
      <h2>Quality impact</h2>
      <div class="md">{_html_escape(run.get("parsed_quality_impact") or "—")}</div>
      <h2>Suggested fix</h2>
      <div class="md">{_html_escape(run.get("parsed_suggested_fix") or "—")}</div>
    </div>
  </div>

  <div class="hallu-list">
    <strong>Hallucination categories (multi-select, enter space-separated indices in console)</strong>
    <ul>{hallu_items}</ul>
  </div>

  <details>
    <summary>Raw LLM output (collapsed)</summary>
    <pre>{_html_escape(run.get("raw_llm_output") or "")}</pre>
  </details>
</body>
</html>"""


def _waiting_html(message: str) -> str:
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="2">
<title>Scoring</title><style>{_HTML_CSS}</style></head>
<body><div class="progress">{_html_escape(message)}</div></body></html>"""


def write_view(view_path: Path, content: str) -> None:
    view_path.write_text(content, encoding="utf-8")


# ── Scoring loop ─────────────────────────────────────────────────────────────

def score_run(run: dict) -> dict | None:
    """Returns the enriched record, or None if skipped. Raises StopIteration on quit."""
    record: dict = dict(run)
    started_at = datetime.now(timezone.utc)
    record["rating_started_at"] = started_at.isoformat()

    # ── Refusal short-circuit ────────────────────────────────────────────────
    is_refusal = detect_refusal(run.get("raw_llm_output") or run.get("parsed_explanation"))
    if is_refusal:
        print("  [auto] refusal detected — pre-filling all dimensions as Poor (rationale: 'refusal').")
        print("         Press Enter to accept; type 'override' to score manually.")
        ans = input("  > ").strip().lower()
        if ans == "quit":     raise StopIteration
        if ans == "skip":     return None
        if ans != "override":
            record.update(auto_refusal_record(run))
            record["rating_completed_at"] = datetime.now(timezone.utc).isoformat()
            record["rating_duration_seconds"] = (
                datetime.now(timezone.utc) - started_at).total_seconds()
            return record

    # ── 8 ordinal dimensions ─────────────────────────────────────────────────
    record["refusal_detected"] = False
    for field, label in ALL_DIMS:
        result = prompt_ordinal(label)
        if result is QUIT: raise StopIteration
        if result is SKIP: return None
        value, rationale, uncertain = result
        record[field]                = value
        record[f"{field}_rationale"] = rationale
        record[f"{field}_uncertain"] = uncertain

    # ── Hallucination categories (multi-label) ───────────────────────────────
    cats = prompt_multi_label_indices(
        "Hallucination categories",
        HALLUCINATION_CATEGORIES,
        HALLUCINATION_DESCRIPTIONS)
    if cats is QUIT: raise StopIteration
    if cats is SKIP: return None
    record["hallucination_categories"] = cats

    # ── Quality-attribute task (§B.7.2) ──────────────────────────────────────
    expected = run.get("expected_quality_attributes") or []
    mentioned = run.get("llm_quality_attributes_mentioned") or []

    print(f"  expected (ground truth) : {expected}")
    print(f"  auto-extracted mentions : {mentioned}")

    aligned_default = len(set(expected) & set(mentioned))
    aligned = prompt_int("Attributes correctly aligned", aligned_default, min_val=0)
    if aligned is QUIT: raise StopIteration
    if aligned is SKIP: return None
    record["attributes_correctly_aligned"] = aligned

    incorrect = prompt_int("Incorrectly mentioned attributes", 0, min_val=0)
    if incorrect is QUIT: raise StopIteration
    if incorrect is SKIP: return None
    record["incorrectly_mentioned_attributes"] = incorrect

    notes = prompt_optional("Notes (optional)")
    record["quality_attribute_notes"] = notes

    # ── Per-row audit fields (§B.10.1) ───────────────────────────────────────
    completed_at = datetime.now(timezone.utc)
    record["rating_completed_at"]      = completed_at.isoformat()
    record["rating_duration_seconds"]  = (completed_at - started_at).total_seconds()
    return record


# ── Driver ───────────────────────────────────────────────────────────────────

def driver(rows: list[dict], output_path: Path, rater_id: str,
           viewer: str, view_path: Path | None) -> int:
    already = read_already_scored(output_path, rater_id)
    if already:
        print(f"resuming — {len(already)} run(s) already scored by {rater_id}, skipping them.")

    pending = [r for r in rows if r.get("run_id") not in already]
    total = len(pending)

    if total == 0:
        print("nothing to score.")
        return 0

    print(f"scoring {total} run(s) — rater = {rater_id}, rubric = v{RUBRIC_VERSION}")
    print(f"output : {output_path.resolve()}")
    print("commands:  Enter = accept default | 'skip' = skip row | 'quit' = save and exit")
    print("ordinal :  p / a / g  (suffix ? for uncertain)")

    if viewer == "html":
        assert view_path is not None
        write_view(view_path, _waiting_html("Loading first run…"))
        url = view_path.resolve().as_uri()
        print(f"viewer : {url}  (auto-refreshes — keep this tab open)")
        try:
            webbrowser.open(url)
        except Exception as ex:
            print(f"  [warn] could not auto-open browser: {ex}")

    scored = 0
    for i, run in enumerate(pending, start=1):
        if viewer == "html":
            write_view(view_path, render_run_html(run, i, total))
        else:
            show_run_console(run, i, total)
        try:
            rec = score_run(run)
        except StopIteration:
            print("\nquit — exiting.")
            break
        if rec is None:
            print("  skipped.")
            continue

        # Attach audit fields and persist.
        rec["rater_id"]        = rater_id
        rec["rubric_version"]  = RUBRIC_VERSION
        rec["rated_at"]        = datetime.now(timezone.utc).isoformat()
        # blinding_lot is already on the row if it came from select_rating_set.py.
        append_record(output_path, rec)
        scored += 1

    if viewer == "html":
        write_view(view_path, _waiting_html(f"Done — {scored} run(s) scored."))

    print(f"\ndone — {scored} run(s) appended to {output_path}")
    return 0


# ── Main ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Score rated outputs under the rubric in Appendix B of the thesis."
    )
    parser.add_argument("--input", "-i", required=True, type=Path,
                        help="experiments_to_rate.jsonl produced by select_rating_set.py")
    parser.add_argument("--output", "-o", default=Path("experiments.jsonl"), type=Path,
                        help="Where to append scored rows (default: experiments.jsonl).")
    parser.add_argument("--rater", default="R1",
                        help="Rater identifier ('R1' = primary, 'R2' = second rater). Default: R1.")
    parser.add_argument("--viewer", choices=["console", "html"], default="html",
                        help="Display mode for each run. Default: html (blinded browser view).")
    parser.add_argument("--view-path", type=Path, default=Path("_scoring_view.html"),
                        help="Auto-refreshing HTML page path (only used with --viewer html).")
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 2

    rows = read_jsonl([args.input])
    if not rows:
        print(f"error: no rows in {args.input}", file=sys.stderr)
        return 2
    print(f"loaded {len(rows)} row(s) from {args.input}")

    # Verify the file came from select_rating_set.py — presentation_index is the marker.
    if not any("presentation_index" in r for r in rows):
        print(f"  [warn] input has no `presentation_index` field — was this produced by "
              f"select_rating_set.py? Rating order may not be stratified.", file=sys.stderr)

    return driver(
        rows, args.output, args.rater,
        viewer=args.viewer,
        view_path=args.view_path if args.viewer == "html" else None,
    )


if __name__ == "__main__":
    raise SystemExit(main())
