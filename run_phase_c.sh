#!/usr/bin/env bash
# run_phase_c.sh — HybridLens Phase C end-to-end pipeline
#
# Usage:
#   bash run_phase_c.sh                          run C-0 → C-4 (automated, all repairs)
#   bash run_phase_c.sh --max-repairs N          repair only N unique instances (e.g. 1 for a smoke test)
#   bash run_phase_c.sh --skip-repair            skip verify-repair entirely (~400 builds, ~1-2 h)
#   bash run_phase_c.sh --dry-run                print commands only, no execution
#   bash run_phase_c.sh --post-rating            run analysis on rated experiments.jsonl
#
# Prerequisites:
#   - dotnet 10 on PATH
#   - python 3 on PATH
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

CORPUS="$Z_DRIVE/GitHub/hybrid-pipeline-corpus/corpus/Corpus.sln"
GROUND_TRUTH="$Z_DRIVE/GitHub/hybrid-pipeline-corpus/ground-truth/records"
CLI="src/HybridLens.CLI"
MODEL="gpt-5.4"
APPLIER="DeepSeek-V4-Pro"
RUNS=3
BUDGET=6   # agentic iteration budget — max edit→build attempts per trajectory (§4.8.1)
MAX_PER_TYPE=10
IRR_FRACTION=0.30
RNG_SEED=42

# ── Parse flags ────────────────────────────────────────────────────────────────
SKIP_REPAIR=0
DRY_RUN=0
POST_RATING=0
MAX_REPAIRS=0   # 0 = repair every candidate; N = repair only N unique instances

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-repair)   SKIP_REPAIR=1;        shift ;;
        --dry-run)       DRY_RUN=1;            shift ;;
        --post-rating)   POST_RATING=1;        shift ;;
        --max-repairs)   MAX_REPAIRS="${2:?'--max-repairs requires a number'}"; shift 2 ;;
        -h|--help)       sed -n '2,9p' "$0";   exit 0 ;;
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
latest_run()      { ls -t runs/[0-9]*.jsonl    2>/dev/null | head -1 || echo ""; }
latest_agentic()  { ls -t runs/*-agentic.jsonl 2>/dev/null | head -1 || echo ""; }
latest_verified() { ls -t runs/*-verified.jsonl 2>/dev/null | head -1 || echo ""; }

# ══════════════════════════════════════════════════════════════════════════════
#  POST-RATING MODE — jump straight to analysis; C-0..C-4 already ran
# ══════════════════════════════════════════════════════════════════════════════
if [[ $POST_RATING -eq 1 ]]; then
    step "C-5  Post-rating analysis"

    [[ -f "experiments.jsonl" ]] \
        || die "experiments.jsonl not found — run R1 rating first (see instructions at end of previous run)"

    # Verified-repair rows come from two sources: the hybrid verify-repair trace AND the agentic
    # trace (the agent's final solutions are scored in-runner, §4.7.1). Combine both for Table 5.3.
    VERIFIED=$(latest_verified)
    AGENTIC=$(latest_agentic)
    VERIFIED_FLAG=""
    if [[ -n "$VERIFIED" || -n "$AGENTIC" ]]; then
        VERIFIED_COMBINED="runs/phase-c-verified-combined.jsonl"
        if [[ $DRY_RUN -eq 0 ]]; then
            : > "$VERIFIED_COMBINED"
            [[ -n "$VERIFIED" ]] && cat "$VERIFIED" >> "$VERIFIED_COMBINED"
            [[ -n "$AGENTIC"  ]] && cat "$AGENTIC"  >> "$VERIFIED_COMBINED"
        fi
        VERIFIED_FLAG="--verified $VERIFIED_COMBINED"
    else
        warn "No verified-repair or agentic trace found; repair tables will be skipped"
    fi

    run "$PYTHON" analysis/analyse_results.py \
        --input  experiments.jsonl \
        --output output \
        $VERIFIED_FLAG
    ok "Tables and figures → output/"

    if [[ -f "experiments_r2.jsonl" ]]; then
        run "$PYTHON" analysis/compare_raters.py \
            --r1 experiments.jsonl \
            --r2 experiments_r2.jsonl \
            --output output/irr
        ok "IRR report → output/irr/"
    else
        warn "experiments_r2.jsonl not found — IRR skipped"
        info "Rate the IRR subset first:"
        info "  python analysis/score_runs.py --input experiments_irr.jsonl --output experiments_r2.jsonl --rater R2"
    fi

    step "Done"
    exit 0
fi

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
info "Runs        : 4 levels × $MAX_PER_TYPE × $RUNS = $((4 * MAX_PER_TYPE * RUNS)) hybrid  +  ~$((MAX_PER_TYPE * 3 * RUNS)) agentic trajectories (each a multi-turn build loop)"
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

# Band agreement: confirm detector metrics match frozen ground truth
run "$PYTHON" analysis/band_agreement.py \
    --runs         "$TRACE_ANALYSER" \
    --ground-truth "$GROUND_TRUTH"
ok "Band agreement: 30/30 expected"

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

# ── C-4: Select rating set ──────────────────────────────────────────────────────
step "C-4  Select rating set"

# Primary set: 1 row per (finding × context_level) cell, fixed random order
run "$PYTHON" analysis/select_rating_set.py \
    --input  "$HYBRID_COMBINED" \
    --output experiments_to_rate.jsonl \
    --seed   $RNG_SEED
ok "Primary set → experiments_to_rate.jsonl"

# Agentic set: matched (recovered) findings only
run "$PYTHON" analysis/select_rating_set.py \
    --agentic \
    --input  "$TRACE_AGENTIC" \
    --output experiments_to_rate_agentic.jsonl \
    --seed   $RNG_SEED
ok "Agentic set → experiments_to_rate_agentic.jsonl"

# 30% stratified IRR subsample from the primary set (for R2)
run "$PYTHON" analysis/select_rating_set.py \
    --irr-from     experiments_to_rate.jsonl \
    --irr-fraction $IRR_FRACTION \
    --output       experiments_irr.jsonl \
    --seed         $RNG_SEED
ok "IRR subset (${IRR_FRACTION}) → experiments_irr.jsonl"

# ── Print what to do next ───────────────────────────────────────────────────────
step "Phase C complete — manual rating required before analysis"
printf '\n'
info "1.  Rate the primary set (R1 — blinded browser view):"
info "      python analysis/score_runs.py \\"
info "          --input experiments_to_rate.jsonl \\"
info "          --output experiments.jsonl --rater R1"
printf '\n'
info "2.  Rate the IRR subset (R2 — second rater):"
info "      python analysis/score_runs.py \\"
info "          --input experiments_irr.jsonl \\"
info "          --output experiments_r2.jsonl --rater R2"
printf '\n'
info "3.  Run analysis after rating:"
info "      bash run_phase_c.sh --post-rating"
printf '\n'
