#!/usr/bin/env bash
# run_experiment.sh — HybridLens end-to-end experiment pipeline.
#
# Runs the stages that produced the reported results, in the order the protocol requires:
# behavioural measurement never happens before every repair condition has terminated.
#
#   1  baseline    detector over the pristine corpus; no model call
#   2  tests       one diagnosis-blind characterisation-test call per target
#   3  manifest    freeze the randomised assignment schedule
#   4  campaign    execute the assignments; seals one final source each
#   5  oracle      private Layer-3 behavioural measurement, post-seal
#   6  analyse     summary, statistics and figures
#
# Usage
#   bash run_experiment.sh                       every stage in order
#   bash run_experiment.sh --stage campaign      one stage only
#   bash run_experiment.sh --from oracle         that stage and everything after
#   bash run_experiment.sh --dry-run             print the commands, execute nothing
#   bash run_experiment.sh --help
#
# Environment overrides (defaults reproduce the reported run)
#   MODEL=gpt-5.6-sol  RUNS=3  BUDGET=6  SEED=503999552  OUT=experiments/<name>
#   CORPUS=<path to Corpus.sln>
#
# A cheap orchestration pilot, one target and one repetition:
#   RUNS=1 MAX_TARGETS=1 bash run_experiment.sh
#
# Prerequisites
#   - dotnet 10 on PATH
#   - python 3 with analysis/requirements.txt installed
#   - src/HybridLens.CLI/appsettings.local.json defining the evaluated model and, for the
#     four-level supplement, the strict-literal applier
#   - the frozen corpus checked out (CORPUS below)
#
# The supplementary four-level experiment and the industrial transfer probe are separate entry
# points, documented in README.md under "Other experiments". They are deliberately not folded in
# here: their denominators are never pooled with the confirmatory factorial.

set -euo pipefail

# ── Environment ────────────────────────────────────────────────────────────────
IS_WSL=0
grep -qi microsoft /proc/version 2>/dev/null && IS_WSL=1
if   [[ $IS_WSL -eq 1 && -d /mnt/z ]]; then Z_DRIVE="/mnt/z"
elif [[ -d /z ]];                      then Z_DRIVE="/z"
else                                        Z_DRIVE="Z:"
fi

CORPUS="${CORPUS:-$Z_DRIVE/GitHub/hybrid-pipeline-corpus/corpus/Corpus.sln}"
CLI="${CLI:-src/HybridLens.CLI}"
MODEL="${MODEL:-gpt-5.6-sol}"
RUNS="${RUNS:-3}"
BUDGET="${BUDGET:-6}"          # iterative build-attempt budget; keep equal across iterative arms
SEED="${SEED:-503999552}"
BUILD_TIMEOUT="${BUILD_TIMEOUT:-180}"
MAX_INPUT_TOKENS="${MAX_INPUT_TOKENS:-120000}"
MAX_TARGETS="${MAX_TARGETS:-0}" # 0 = every target in the baseline
STAMP="$(date -u +%Y%m%d)"
OUT="${OUT:-experiments/run-$STAMP}"

BASELINE="$OUT/baseline.jsonl"
TESTS_DIR="$OUT/generated-tests"
MANIFEST="$OUT/factorial-manifest.json"
CAMPAIGN="$OUT/campaign"
PRIVATE_DIR="$OUT/private-results"
RESULTS="$OUT/results"

STAGES=(baseline tests manifest campaign oracle analyse)

# ── Flags ──────────────────────────────────────────────────────────────────────
DRY_RUN=0
ONLY_STAGE=""
FROM_STAGE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --stage)   ONLY_STAGE="${2:?--stage needs a stage name}"; shift 2 ;;
        --from)    FROM_STAGE="${2:?--from needs a stage name}";  shift 2 ;;
        --help|-h) sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
    esac
done

# ── Helpers ────────────────────────────────────────────────────────────────────
step() { printf '\n\e[1;34m══ %s\e[0m\n' "$*"; }
info() { printf '   %s\n' "$*"; }
die()  { printf '\e[1;31merror: %s\e[0m\n' "$*" >&2; exit 1; }

run() {
    if [[ $DRY_RUN -eq 1 ]]; then printf '   $ %s\n' "$*"; return 0; fi
    "$@"
}

wants() {
    local stage="$1" i want_index=0 stage_index=0
    [[ -n "$ONLY_STAGE" ]] && { [[ "$ONLY_STAGE" == "$stage" ]]; return; }
    [[ -z "$FROM_STAGE" ]] && return 0
    for i in "${!STAGES[@]}"; do
        [[ "${STAGES[$i]}" == "$FROM_STAGE" ]] && want_index=$i
        [[ "${STAGES[$i]}" == "$stage"      ]] && stage_index=$i
    done
    (( stage_index >= want_index ))
}

validate_stage_name() {
    local name="$1" s
    [[ -z "$name" ]] && return 0
    for s in "${STAGES[@]}"; do [[ "$s" == "$name" ]] && return 0; done
    die "unknown stage '$name'. Known stages: ${STAGES[*]}"
}

# ── Preconditions ──────────────────────────────────────────────────────────────
step "HybridLens experiment pipeline"
validate_stage_name "$ONLY_STAGE"
validate_stage_name "$FROM_STAGE"

command -v dotnet >/dev/null || die "dotnet not found on PATH."
PYTHON="${PYTHON:-}"
[[ -z "$PYTHON" ]] && command -v python3 >/dev/null && PYTHON="python3"
[[ -z "$PYTHON" ]] && command -v python  >/dev/null && PYTHON="python"
[[ -n "$PYTHON" ]] || die "python 3 not found on PATH."
[[ -f "$CORPUS" ]] || die "corpus solution not found: $CORPUS"
[[ -f "$CLI/appsettings.local.json" ]] || \
    die "$CLI/appsettings.local.json is missing; the evaluated model must be configured."

CODE_REVISION="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

info "corpus        $CORPUS"
info "model         $MODEL"
info "runs          $RUNS      budget $BUDGET      seed $SEED"
info "output        $OUT"
info "code revision $CODE_REVISION"
[[ $DRY_RUN -eq 1 ]] && info "DRY RUN — no command will be executed"
run mkdir -p "$OUT"

# ── 1. Detector baseline ───────────────────────────────────────────────────────
if wants baseline; then
    step "1  Detector baseline (no model call)"
    info "Establishes which targets exist and supplies the Structural finding to grounded cells."
    run dotnet run --project "$CLI" -- analyse \
        --target "$CORPUS" --dry-run --severity Warning \
        --format json --output "$BASELINE"
fi

# ── 2. Characterisation-test generation ────────────────────────────────────────
if wants tests; then
    step "2  Diagnosis-blind characterisation tests (one call per target)"
    info "The generator never sees the anti-pattern label, the finding, a metric or a repair."
    info "Generation is attempted once per target; a rejected artefact is never regenerated, and"
    info "its assignments stay in the test-ON denominator under intention to treat."
    run mkdir -p "$TESTS_DIR"
    if [[ $DRY_RUN -eq 1 ]]; then
        info '$ for each target source: generate-characterization-test --source <file> ...'
    else
        mapfile -t SOURCES < <("$PYTHON" - "$BASELINE" <<'PY'
import json, sys
findings = json.load(open(sys.argv[1], encoding='utf-8-sig'))['findings']
seen = []
for f in findings:
    if f['type'] in ('longMethod', 'godClass') and f['filePath'] not in seen:
        seen.append(f['filePath'])
print('\n'.join(seen))
PY
        )
        [[ ${#SOURCES[@]} -gt 0 ]] || die "no Long Method or God Class target in $BASELINE"
        (( MAX_TARGETS > 0 )) && SOURCES=("${SOURCES[@]:0:$MAX_TARGETS}")
        info "${#SOURCES[@]} target source file(s)"
        CORPUS_ROOT="$(dirname "$CORPUS")"
        for source in "${SOURCES[@]}"; do
            info "generating for $source"
            dotnet run --project "$CLI" -- generate-characterization-test \
                --from "$BASELINE" --target "$CORPUS" \
                --source "$CORPUS_ROOT/$source" --model "$MODEL" --out "$TESTS_DIR" \
                || info "  admission failed; retained as unavailable (intention to treat)"
        done
    fi
fi

# ── 3. Frozen assignment schedule ──────────────────────────────────────────────
if wants manifest; then
    step "3  Freeze the assignment schedule"
    info "Blocks on (target, repetition) and crosses the design within each block."
    run dotnet run --project "$CLI" -- factorial-manifest \
        --from "$BASELINE" --target "$CORPUS" --visible-tests "$TESTS_DIR" \
        --model "$MODEL" --code-revision "$CODE_REVISION" \
        --runs "$RUNS" --budget "$BUDGET" --build-timeout "$BUILD_TIMEOUT" \
        --max-input-tokens "$MAX_INPUT_TOKENS" --seed "$SEED" --out "$MANIFEST"
    info "Inspect it before spending model calls:"
    info "  dotnet run --project $CLI -- factorial-campaign --manifest $MANIFEST --out $CAMPAIGN --dry-run"
fi

# ── 4. Repair campaign ─────────────────────────────────────────────────────────
if wants campaign; then
    step "4  Repair campaign"
    info "One assignment at a time, crash-safe: an interrupted run resumes from its ledger and"
    info "never repeats a committed assignment. Detector and private-oracle results are withheld"
    info "from every model call."
    run dotnet run --project "$CLI" -- factorial-campaign \
        --manifest "$MANIFEST" --out "$CAMPAIGN"
fi

# ── 5. Post-seal behavioural measurement ───────────────────────────────────────
if wants oracle; then
    step "5  Private Layer-3 behavioural measurement (post-seal)"
    info "Runs only after every repair condition has terminated, so no repair can be tuned to it."
    run mkdir -p "$PRIVATE_DIR"
    run dotnet run --project "$CLI" -- private-layer3 \
        --artifacts "$CAMPAIGN/final-sources" --target "$CORPUS" \
        --out "$PRIVATE_DIR/private-layer3.jsonl"
fi

# ── 6. Analysis ────────────────────────────────────────────────────────────────
if wants analyse; then
    step "6  Summary, statistics and figures"
    run mkdir -p "$RESULTS"
    run dotnet run --project "$CLI" -- factorial-summary \
        --runs-dir "$CAMPAIGN/traces" --private-dir "$PRIVATE_DIR" --out "$RESULTS"
    info "Repair shape — settles the gaming question of the metric-resolved outcome:"
    run "$PYTHON" analysis/extraction_vs_simplification.py --campaign "$OUT"
    info "Paired effects, the mixed-model sensitivity analysis and the figures:"
    info "  $PYTHON analysis/analyse_results.py --help"
    info "  $PYTHON analysis/factorial_glmm.py --help"
    info "  $PYTHON analysis/sol_thesis_figures.py --help"
fi

step "Done"
info "output tree     $OUT"
[[ $DRY_RUN -eq 1 ]] && info "nothing was executed (--dry-run)"
exit 0
