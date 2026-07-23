#!/usr/bin/env bash
# run_phase_c.sh — HybridLens Phase C end-to-end pipeline
#
# Usage:
#   bash run_phase_c.sh                          run the complete automated pipeline
#   bash run_phase_c.sh --max-repairs N          repair only N unique instances (e.g. 1 for a smoke test)
#   bash run_phase_c.sh --skip-repair            skip verify-repair entirely (~400 builds, ~1-2 h)
#   bash run_phase_c.sh --dry-run                print commands only, no execution
#   MAX_PER_TYPE=1 RUNS=1 bash run_phase_c.sh     cheap pilot of the whole pipeline (env overrides)
#
# Prerequisites:
#   - dotnet 10 on PATH
#   - python 3 on PATH with analysis/requirements.txt installed
#   - src/HybridLens.CLI/appsettings.local.json with Llm.ApiKey set
#   - Corpus at Z:/GitHub/hybrid-pipeline-corpus/corpus/Corpus.sln

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────────────────
# Detect environment: WSL vs Git Bash on Windows
IS_WSL=0
grep -qi microsoft /proc/version 2>/dev/null && IS_WSL=1

# Resolve Z: drive: WSL → /mnt/z, Git Bash → /z, Windows fallback → Z:
if   [[ $IS_WSL -eq 1 && -d "/mnt/z" ]]; then Z_DRIVE="/mnt/z"
elif [[ -d "/z" ]];                             then Z_DRIVE="/z"
else                                                 Z_DRIVE="Z:"
fi

# All overridable from the environment (defaults preserve the full-scale thesis run). Handy for a
# cheap orchestration pilot: MAX_PER_TYPE=1 RUNS=1 bash run_phase_c.sh
CORPUS="${CORPUS:-$Z_DRIVE/GitHub/hybrid-pipeline-corpus/corpus/Corpus.sln}"
# band_agreement.py appends "/records" itself, so this must be the ground-truth ROOT, not .../records
# (passing .../records made it glob .../records/records → 0 truth records → the gate passed vacuously).
GROUND_TRUTH="${GROUND_TRUTH:-$Z_DRIVE/GitHub/hybrid-pipeline-corpus/ground-truth}"
CLI="${CLI:-src/HybridLens.CLI}"
MODEL="${MODEL:-gpt-5.4}"
APPLIER="${APPLIER:-DeepSeek-V4-Pro}"
RUNS="${RUNS:-3}"
BUDGET="${BUDGET:-6}"   # agentic iteration budget — max edit→build attempts per trajectory (§4.8.1); keep equal across the agentic + grounded-iterative arms
MAX_PER_TYPE="${MAX_PER_TYPE:-10}"

# ── Parse flags ────────────────────────────────────────────────────────────────
SKIP_REPAIR=0
DRY_RUN=0
MAX_REPAIRS=0   # 0 = repair every candidate; N = repair only N unique instances

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-repair)   SKIP_REPAIR=1;        shift ;;
        --dry-run)       DRY_RUN=1;            shift ;;
        --max-repairs)   MAX_REPAIRS="${2:?'--max-repairs requires a number'}"; shift 2 ;;
        -h|--help)       sed -n '2,10p' "$0";  exit 0 ;;
        *) printf 'Unknown flag: %s\n' "$1" >&2; exit 2 ;;
    esac
done

# ── Resolve python ────────────────────────────────────────────────────────────
# WSL/Linux uses python3; Windows Git Bash may only have python
PYTHON=""
command -v python3 &>/dev/null && PYTHON="python3"
command -v python  &>/dev/null && [[ -z "$PYTHON" ]] && PYTHON="python"

# ── Resolve dotnet ────────────────────────────────────────────────────────────
# In WSL without a Linux .NET install, Windows dotnet.exe is available via interop.
DOTNET=""
command -v dotnet     &>/dev/null && DOTNET="dotnet"
command -v dotnet.exe &>/dev/null && [[ -z "$DOTNET" ]] && DOTNET="dotnet.exe"

# When using dotnet.exe from WSL, file paths must be Windows-formatted.
# wslpath -w converts /mnt/z/foo → Z:\foo.  Passes through unchanged otherwise.
winpath() {
    if [[ $IS_WSL -eq 1 && "$DOTNET" == "dotnet.exe" ]]; then
        wslpath -w "$1"
    else
        printf '%s' "$1"
    fi
}

# ── Terminal helpers ───────────────────────────────────────────────────────────
step()  { printf '\n\e[1;34m══ %s\e[0m\n' "$*"; }
ok()    { printf '  \e[32m✓\e[0m  %s\n'   "$*"; }
info()  { printf '  \e[36m→\e[0m  %s\n'   "$*"; }
warn()  { printf '  \e[33m!\e[0m  %s\n'   "$*" >&2; }
die()   { printf '\e[31m✗ %s\e[0m\n'      "$*" >&2; exit 1; }

# analyse returns exit 1 when findings exist — not an error
run_analyse() {
    if [[ $DRY_RUN -eq 1 ]]; then
        info "$DOTNET run --project $CLI -- analyse $*"; return 0
    fi
    "$DOTNET" run --project "$CLI" -- analyse "$@" || {
        local rc=$?; [[ $rc -eq 1 ]] || die "analyse failed (exit $rc)"; }
}

run() {
    if [[ $DRY_RUN -eq 1 ]]; then info "$*"; return 0; fi
    "$@"
}

# Most recently modified JSONL by naming convention
latest_run() {
    local trace
    while IFS= read -r trace; do
        case "$trace" in
            *-agentic.jsonl|*-grounded-iterative.jsonl|*-verified.jsonl) continue ;;
            *) printf "%s\n" "$trace"; return ;;
        esac
    done < <(ls -t runs/[0-9]*.jsonl 2>/dev/null)
}
latest_agentic()  { ls -t runs/*-agentic.jsonl 2>/dev/null | head -1 || echo ""; }
latest_grounded() { ls -t runs/*-grounded-iterative.jsonl 2>/dev/null | head -1 || echo ""; }
latest_verified() { ls -t runs/*-verified.jsonl 2>/dev/null | head -1 || echo ""; }

# ══════════════════════════════════════════════════════════════════════════════
#  AUTOMATED RUN — C-0 through C-4
# ══════════════════════════════════════════════════════════════════════════════

step "HybridLens Phase C — automated pipeline"
[[ -f "$CORPUS" ]] || die "Corpus not found: $CORPUS"
[[ -n "$DOTNET"  ]] || die "dotnet not found on PATH. Install .NET 10 SDK (or run from Git Bash instead of WSL)."
[[ -n "$PYTHON"  ]] || die "python not found on PATH. Install Python 3."
[[ $IS_WSL -eq 1 && "$DOTNET" == "dotnet.exe" ]] \
    && warn "WSL + Windows interop: using dotnet.exe, paths converted via wslpath"
[[ -f "$CLI/appsettings.local.json" ]] \
    || warn "appsettings.local.json missing — Azure key may not be set"
mkdir -p runs output

info "Corpus      : $CORPUS"
info "Model       : $MODEL  (evaluated)"
info "Applier     : $APPLIER  (repair only, not evaluated)"
info "Runs/finding: $RUNS"
info "Cap/type    : $MAX_PER_TYPE  (${MAX_PER_TYPE}×3 = $((MAX_PER_TYPE * 3)) findings total)"
info "Runs        : 4 levels × $MAX_PER_TYPE × $RUNS = $((4 * MAX_PER_TYPE * RUNS)) hybrid  +  ~$((MAX_PER_TYPE * 3 * RUNS)) agentic  +  ~$((MAX_PER_TYPE * 3 * RUNS)) grounded-iterative trajectories (each a multi-turn build loop)"
[[ $MAX_REPAIRS -gt 0 ]] && info "Repairs     : $MAX_REPAIRS unique instance(s) (--max-repairs)"
[[ $SKIP_REPAIR -eq 1 ]] && warn "verify-repair SKIPPED (--skip-repair)"
[[ $DRY_RUN -eq 1 ]]     && warn "DRY RUN — no commands will execute"
ok "Pre-flight passed"

# ── C-0: Analyser-only baseline ─────────────────────────────────────────────────
step "C-0  Analyser-only baseline (no LLM — establishes arm 0)"
run_analyse \
    --target "$(winpath "$CORPUS")" \
    --context-level analyser-only \
    --severity Warning \
    --max-findings-per-type $MAX_PER_TYPE

TRACE_ANALYSER=$(latest_run)
ok "Trace: $TRACE_ANALYSER"

# Band agreement: confirm detector metrics match the frozen ground truth. It checks the run trace
# against ALL 30 truth records and fails unless every one agrees, so it's only meaningful at full
# scale — skip it on a partial pilot (MAX_PER_TYPE < 10), where the sample can't cover all 30.
if [[ $MAX_PER_TYPE -ge 10 ]]; then
    run "$PYTHON" analysis/band_agreement.py \
        --runs         "$TRACE_ANALYSER" \
        --ground-truth "$GROUND_TRUTH"
    ok "Band agreement: 30/30 expected"
else
    warn "Band agreement skipped (pilot: MAX_PER_TYPE=$MAX_PER_TYPE < 10 can't cover all 30 truth records)"
fi

# ── C-1: Hybrid arm — 4 context levels ─────────────────────────────────────────
step "C-1  Hybrid arm"

info "minimal  ($MAX_PER_TYPE findings × $RUNS runs)"
run_analyse \
    --target "$(winpath "$CORPUS")" --model "$MODEL" \
    --context-level minimal \
    --severity Warning --max-findings-per-type $MAX_PER_TYPE --runs $RUNS
TRACE_MINIMAL=$(latest_run)
ok "minimal → $TRACE_MINIMAL"

info "structural  ($MAX_PER_TYPE findings × $RUNS runs)"
run_analyse \
    --target "$(winpath "$CORPUS")" --model "$MODEL" \
    --context-level structural \
    --severity Warning --max-findings-per-type $MAX_PER_TYPE --runs $RUNS
TRACE_STRUCTURAL=$(latest_run)
ok "structural → $TRACE_STRUCTURAL"

info "relational  ($MAX_PER_TYPE findings × $RUNS runs)"
run_analyse \
    --target "$(winpath "$CORPUS")" --model "$MODEL" \
    --context-level relational \
    --severity Warning --max-findings-per-type $MAX_PER_TYPE --runs $RUNS
TRACE_RELATIONAL=$(latest_run)
ok "relational → $TRACE_RELATIONAL"

info "full  ($MAX_PER_TYPE findings × $RUNS runs)"
run_analyse \
    --target "$(winpath "$CORPUS")" --model "$MODEL" \
    --context-level full \
    --severity Warning --max-findings-per-type $MAX_PER_TYPE --runs $RUNS
TRACE_FULL=$(latest_run)
ok "full → $TRACE_FULL"

HYBRID_COMBINED="runs/phase-c-hybrid-combined.jsonl"
if [[ $DRY_RUN -eq 0 ]]; then
    cat "$TRACE_MINIMAL" "$TRACE_STRUCTURAL" "$TRACE_RELATIONAL" "$TRACE_FULL" \
        > "$HYBRID_COMBINED"
    ok "Combined: $HYBRID_COMBINED  ($(wc -l < "$HYBRID_COMBINED") rows)"
else
    info "cat <4 traces> > $HYBRID_COMBINED"
fi

# ── C-2: Agentic arm ───────────────────────────────────────────────────────────
step "C-2  Agentic arm (whole-file autonomous detect-and-repair loop, no static grounding)"
info "$((MAX_PER_TYPE * 3)) instance files × $RUNS trajectories, budget=$BUDGET build attempts each"
run "$DOTNET" run --project "$CLI" -- agentic \
    --from   "$(winpath "$TRACE_STRUCTURAL")" \
    --target "$(winpath "$CORPUS")" \
    --model  "$MODEL" \
    --runs   $RUNS \
    --budget $BUDGET

TRACE_AGENTIC=$(latest_agentic)
ok "Agentic → $TRACE_AGENTIC"

# ── C-2b: Grounded-iterative arm (H1c) ──────────────────────────────────────────
# Same loop + budget as the agentic arm, but the opening prompt is seeded with the analyser's
# Structural finding block, so it varies grounding alone (§4.4.1, §5.1.5). --from the structural
# trace supplies each instance's detector metrics for that block. Populates the grounded row of the
# §4.4.1 2×2 (Table 5.7); its first_build snapshot is decomposed in-runner beside the final one.
step "C-2b  Grounded-iterative arm (analyser-grounded autonomous repair loop — the H1c contrast)"
info "$((MAX_PER_TYPE * 3)) instance files × $RUNS trajectories, budget=$BUDGET (must match the agentic arm)"
run "$DOTNET" run --project "$CLI" -- grounded-iterative \
    --from   "$(winpath "$TRACE_STRUCTURAL")" \
    --target "$(winpath "$CORPUS")" \
    --model  "$MODEL" \
    --runs   $RUNS \
    --budget $BUDGET

TRACE_GROUNDED=$(latest_grounded)
ok "Grounded-iterative → $TRACE_GROUNDED"

# ── C-3: Verify-repair ──────────────────────────────────────────────────────────
TRACE_VERIFIED=""
if [[ $SKIP_REPAIR -eq 0 ]]; then
    step "C-3  Verify-repair (apply → dotnet build → re-measure)"

    REPAIR_INPUT="$HYBRID_COMBINED"

    # --max-repairs N: pick the first N unique instances from the combined run,
    # preferring the structural-level/run-1 row for each one. This lets you do a
    # quick smoke test (e.g. --max-repairs 1) without waiting for all ~120 builds.
    if [[ $MAX_REPAIRS -gt 0 ]]; then
        REPAIR_INPUT="runs/phase-c-repair-sample-${MAX_REPAIRS}.jsonl"
        info "Filtering to $MAX_REPAIRS unique instance(s) → $REPAIR_INPUT"

        if [[ $DRY_RUN -eq 0 ]]; then
            _filter=$(mktemp /tmp/hl-filter-XXXXXX.py)
            cat > "$_filter" << 'PYEOF'
import sys, json
from collections import OrderedDict

n_max  = int(sys.argv[1])
in_p   = sys.argv[2]
out_p  = sys.argv[3]

# Collect all eligible rows, grouped by unique instance.
# Key: (symbol_name, anti_pattern_type) — one instance regardless of level/run.
instances = OrderedDict()

with open(in_p) as fh:
    for raw in fh:
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not (row.get('parsed_suggested_fix') or '').strip():
            continue
        if row.get('verified_repair_ladder') is not None:
            continue

        key   = (row.get('symbol_name', ''), row.get('anti_pattern_type', ''))
        level = (row.get('context_level') or '').lower().replace('_', '')
        run_n = row.get('run_number', 99)

        # Lower score = preferred. Prefer structural context, then run 1.
        score = (0 if level == 'structural' else 1, run_n)

        if key not in instances or score < instances[key][0]:
            instances[key] = (score, raw)

selected = [raw for _, raw in list(instances.values())[:n_max]]

with open(out_p, 'w') as fh:
    for line in selected:
        fh.write(line + '\n')

print(f'Selected {len(selected)} unique instance(s) for repair', file=sys.stderr)
PYEOF
            "$PYTHON" "$_filter" "$MAX_REPAIRS" "$HYBRID_COMBINED" "$REPAIR_INPUT"
            rm -f "$_filter"
            ok "Repair input: $REPAIR_INPUT  ($(wc -l < "$REPAIR_INPUT") row(s))"
        else
            info "python <filter> $MAX_REPAIRS $HYBRID_COMBINED $REPAIR_INPUT"
        fi
    fi

    MAX_BUILDS=$(( MAX_REPAIRS > 0 ? MAX_REPAIRS : 4 * MAX_PER_TYPE * RUNS ))
    info "Source : $REPAIR_INPUT"
    info "Builds : up to $MAX_BUILDS candidate(s)"
    run "$DOTNET" run --project "$CLI" -- verify-repair \
        --from   "$(winpath "$REPAIR_INPUT")" \
        --target "$(winpath "$CORPUS")" \
        --applier "$APPLIER"
    TRACE_VERIFIED=$(latest_verified)
    ok "Verified → $TRACE_VERIFIED"
else
    warn "C-3 skipped (--skip-repair)"
fi

# ── C-4: Automated quality evaluation ───────────────────────────────────────────────
step "C-4  Automated quality evaluation"

EVALUATION_INPUT="runs/phase-c-evaluation-combined.jsonl"
if [[ $DRY_RUN -eq 0 ]]; then
    : > "$EVALUATION_INPUT"
    for trace in "$TRACE_ANALYSER" "$HYBRID_COMBINED" "$TRACE_AGENTIC" "$TRACE_GROUNDED" "$TRACE_VERIFIED"; do
        [[ -n "$trace" && -f "$trace" ]] && cat "$trace" >> "$EVALUATION_INPUT"
    done
    ok "Evaluation input: $EVALUATION_INPUT  ($(wc -l < "$EVALUATION_INPUT") rows)"
else
    info "combine raw and verified traces → $EVALUATION_INPUT"
fi

run "$PYTHON" analysis/analyse_results.py \
    --input "$EVALUATION_INPUT" \
    --output output
ok "Automated reports → output/tables/"

run "$PYTHON" analysis/architecture_figure.py --out-dir output/figures
ok "Architecture figure → output/figures/fig_architecture.*"

step "Phase C complete"
info "All configured stages completed without an interactive handoff."
info "Failures and low-confidence conditions remain in the run records; they do not block report generation."
