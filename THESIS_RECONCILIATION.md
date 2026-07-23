# Thesis ⇄ Implementation Reconciliation

**Source of truth:** the thesis PDF (`Z:\rayen\Combining_Static_Analysis_..._(14).pdf`, "Version of 23rd June 2026").
**Goal of this doc:** decisions taken + an executable plan to bring the implementation, data, and thesis text into agreement.

> **⚠ SUPERSEDED for the third arm (2026-06-30).** The newer thesis (version 18) replaced the
> single-shot **LLM-only** arm with the autonomous **Agentic** arm (§4.4.1, Appendix E prompt
> **v2.0.0**): a compiler-in-the-loop detect-and-repair agent whose final edited solution is scored
> directly (no separate applier, §4.7.1). The implementation now matches it — CLI `agentic`,
> `AgenticRunner`, architecture tag `agentic`. Every "LLM-only / v1.2.0" reference **below** is
> historical (it describes the version-14 reconciliation); see `agentic-arm-replaces-llm-only` (memory)
> and the current §3 of [PHASE_C_RUNBOOK.md](PHASE_C_RUNBOOK.md). Lines describing the *current* built
> state have been updated in place.

> Read first: the constructed corpus is **already built and faithful** to the thesis (separate repo `Z:\GitHub\hybrid-pipeline-corpus`). The detectors, context levels, and prompts (v1.1.0 hybrid; the third arm is now agentic v2.0.0) in the pipeline **already match** the thesis. The real work is the verified-repair pipeline, re-pointing experiments at the corpus on a single model, and a batch of thesis-text fixes.

---

## Decisions log

| # | Topic | Decision |
|---|---|---|
| 1 | Output | Decisions + executable work plan (this doc). |
| 2 | Constructed corpus | Already built & authoritative. No rebuild. |
| 3 | Verified-repair pipeline | **Build it now** (thesis's primary objective metric). |
| 4 | Applier model | **DeepSeek-V4-Pro** (Azure; non-evaluated, different family from the evaluated gpt-5.4). Runs on the existing Azure config — no Anthropic key. |
| 5 | Frontier model | **gpt-5.4** via Azure OpenAI — single model for hybrid *and* LLM-only. |
| 6 | Multi-model | **Strictly single model.** Drop the 3-model H1a robustness check; purge cross-model code/analysis. |
| 7 | Dataset | **Discard the Ibis runs** (smoke tests). Corpus is the only dataset. |
| 8 | Band-verification | **Done (2026-06-23):** HybridLens made authoritative — corpus `measured_metrics` re-derived from the real detector (10 records corrected: 9 GodClass ATFD/WMC + 1 LongMethod CC); band agreement now **30/30**; §4.5.1 "same code" holds. `HybridLensMeasure` retained as a generation-time helper. Corpus repo needs commit + re-tag. |
| 9 | Thesis edits | **Punch-list only** (PDF; section-referenced edits below). |

---

## What is already done (no work)

- **Corpus** `Z:\GitHub\hybrid-pipeline-corpus`: 5 compiling .NET 8 projects in `corpus/Corpus.sln` (Ordering, Invoicing, Inventory, Scheduling, Notifications); 30 seeded instances (GC-01..10, LM-01..10, OB-01..10); 31 clean/distractor files; generator `claude-opus-4-8`; frozen `v1.0` (2026-06-17); MIT; frozen v1.0.0 generation prompts; truth-record schema + 30 populated records; verification harness (`tools/*.py`, `tools/Measure`).
- **Thresholds match** the pipeline exactly: ATFD>4, WMC≥47, TCC<1/3, CC>10, LOC>50.
- **Detectors** (ATFD/WMC/TCC composite God Class; CC-primary + LOC-secondary Long Method; `[Obsolete]` semantic Obsolete-API), **context levels** (Minimal/Structural/Relational/Full + AnalyserOnly), and **prompts** (`PromptTemplate.Version = v1.1.0`, `LlmOnlyVersion = v1.2.0`) all match the thesis.
- **Quality-attribute map** matches Table 5.11 (GodClass→Maintainability/Modularity/Analysability/Modifiability; LongMethod→Maintainability/Analysability/Testability/Modifiability; ObsoleteApiUsage→Maintainability/Security/Reliability/Compatibility).

---

## Work plan (ordered)

### Phase A — Verified-repair pipeline (biggest gap)
Implements the thesis spine for H1a (repair), H1b (repair), H2b.

> **Status: implemented & unit-tested (2026-06-23).** New `verify-repair` CLI command +
> `RepairVerifier` (apply → build gate → re-measure → ladder + binary), `RepairApplier` (frozen
> applier prompt v1.0.0), `RoslynRepairMeasurer` behind an `IRepairMeasurer` seam, and the
> `RunRecord` verification fields + `VerifiedRepairOutcome` enum. 39 tests green (13 new).
> **End-to-end smoke-tested (2026-06-23)** on the corpus: load + detection reproduced GC-07's truth
> metrics (ATFD=5/WMC=49/TCC=0.3), `gpt-5.4` produced a parseable repair, and `verify-repair` (with a
> stand-in `gpt-5.4-mini` applier) correctly returned *unapplicable* for a multi-file God Class repair,
> and a Long Method instance (`InvoiceRenderer.Render`, CC 15) went applied → built → **resolved**
> (CC dropped ≤10) — so all four ladder rungs are validated (two live, two via unit tests), incl. the
> `dotnet build` gate and Roslyn re-measure on real corpus code. Remaining: a faithful run needs the
> Phase C corpus dataset (the applier `DeepSeek-V4-Pro` is already in your Azure config — no Anthropic key needed). The
> `analyse_results.py` verified-repair stats (**step 6, done 2026-06-23**: Tables 5.3/5.7 with Wilson CIs,
> McNemar H1b, Cochran–Armitage + GLMM long-format H2b — unit-tested on synthetic data, run via
> `--verified`) and the `--model` filter (Phase B) are now implemented.

1. **Applier adapter + prompt.** Add an applier (`DeepSeek-V4-Pro`, Azure) using the frozen **applier prompt v1.0.0** (thesis Appendix A.1). Contract: input = original file + finding + candidate repair; output = `{applicable, reason_if_not, edited_file}`. Strict-literal; no design decisions. Freeze each applier output as an artefact.
2. **Build gate.** Apply `edited_file` into a **working copy** of the corpus (never mutate the frozen corpus), then `dotnet build`. Build failure ⇒ scored as not-resolved.
3. **Re-measure.** On a green build, re-run the HybridLens detector on the applied file and recompute the triggering condition: GC composite (ATFD/WMC/TCC), LM (CC + LOC), OB (absence of the flagged `[Obsolete]` usage).
4. **Outcome.** Ordinal ladder `unapplicable < build_fails < builds_unresolved < resolved` (descriptive) + binary `verified_repair_success = applies ∧ builds ∧ metric_resolved` (inferential).
5. **RunRecord fields** (new): `applier_model`, `applier_prompt_version`, `applicable`, `unapplicable_reason`, `applied_source_ref`, `build_passed`, `remeasured_metrics`, `verified_repair_ladder`, `verified_repair_success`.
6. **Stats in `analyse_results.py`:** verified-repair % by architecture (Table 5.3) and by context level (Table 5.7) with Wilson CIs; **McNemar** paired hybrid vs agentic (H1b); **Cochran–Armitage** + **binomial GLMM** `verified_repair ~ ordered context + (1|instance)` (H2b); ladder distribution descriptive.
8. Apply/verify for **both** hybrid and LLM-only repairs; analyser-only = no repair (0 by construction).

### Phase B — Single-model + corpus wiring

> **Status: implemented (2026-06-23).** Rather than trimming `Llm.Models` (item 9), added a `--model`
> filter to `analyse` (+ a `models` param on `AnalysisPipeline.RunAsync`) so generation can be pinned to
> `gpt-5.4` while `DeepSeek-V4-Pro` stays configured for the verify-repair applier. Cross-model analysis
> purged: `loader.cross_model_agreement`, the `analyse_results.py` by-model proportions block + the now-unused
> `MODEL_ORDER`, the `compare.py` caller, and the `analysis/README.md` mentions (incl. the cross-model
> Cochran's Q note). Architecture tagging (item 11) was already correct in code — the null was stale Ibis
> data; live runs tag `hybrid` / `analyser_only` / `agentic`. Item 12 is an invocation detail
> (`analyse --model gpt-5.4 --target …\Corpus.sln`). Build green, 39 tests pass. The §4.4.1 "across all
> three models" sentence → thesis punch-list (Phase F).

9. Config: **gpt-5.4** (Azure) is the evaluated model; **DeepSeek-V4-Pro** (Azure) is the applier. Generation is restricted to gpt-5.4 via `--model` (gpt-5.4-mini / Llama / Mistral unused); both arms run on the existing Azure config.
10. **Purge cross-model**: remove `loader.cross_model_agreement` and any cross-model outputs in `analyse_results.py`; delete the §4.4.1 "across all three models" robustness path.
11. Ensure `AnalysisPipeline` **populates `Architecture`** (`analyser_only` / `hybrid` / `agentic`) — currently null in all data.
12. Point runs at `Z:\GitHub\hybrid-pipeline-corpus\corpus\Corpus.sln`.

### Phase C — Regenerate dataset
13. **Discard/retire Ibis data**: `analysis/experiments.json` and `src/runs-archive-pre-v1.1.0/` (already partly archived). Corpus only.
14. Run, all on gpt-5.4, `--runs 3`:
    - **Hybrid:** 30 × 4 context levels × 3 = **360** generations (prompt v1.1.0).
    - **Analyser-only:** 30 deterministic diagnostics (also serves the band re-confirmation in step 17).
    - **LLM-only:** prompt v1.2.0 over the **whole corpus** via `llm-only --target Corpus.sln` — recall over the 30 instances + precision over clean/distractors (resolved 2026-06-23).

### Phase D — Detector agreement
15. **[Done 2026-06-23.]** Ran analyser-only (real HybridLens) over the corpus; `HybridLensMeasure` diverged on GodClass ATFD/WMC + 1 LongMethod CC (10/30; detection unaffected). Re-derived `measured_metrics` from HybridLens (`hybrid-pipeline-corpus/tools/apply_hybridlens_metrics.py`), regenerated INDEX, re-validated → **band agreement 30/30**. Corpus repo: commit + re-tag pending.

### Phase F — Docs
19. `README.md`: fix God Class config (ATFD/WMC/TCC, not Methods/Fields/LOC); default provider `claude`→`azure`/`gpt-5.4`; note context `Level` default.
20. Deliver the thesis punch-list below.

---

## Thesis text punch-list (PDF; section-referenced)

> **Finalized as [THESIS_PUNCHLIST.md](THESIS_PUNCHLIST.md) (2026-06-23)** — the standalone doc has the full
> find→replace text with corpus-verified values, plus corpus-repo follow-ups. The table below is the summary.

| Location | Current | Change to |
|---|---|---|
| §4.3 | "borderline (**4 per type**) and clear-cut (**6 per type**)" | GC & LM = **5 clear-cut + 5 borderline** each; **OB = 10 clear-cut** (borderline N/A for a binary `[Obsolete]` marker), stratified by replacement availability (direct 4 / workaround 3 / removed 3). Net **20 clear-cut / 10 borderline**. |
| §4.3, §5.2.3 | "around **twelve** files without any seeded instances" | "**31** clean/distractor files." |
| §4.3, §5.2.3 | "**Four to six** independently compilable **solutions**" | "**one** solution (`Corpus.sln`) with **five** independently compilable .NET 8 **projects**, 11–14 files each (61 total)." |
| §5.2.3, §5.2.4 placeholders | `[N]`, `[F]`, `[C]`, `[exact Claude model + version]` | `[N]`=5 projects; `[C]`=31; generator=`claude-opus-4-8`; prompt_template_version 1.0.0; frozen v1.0 (2026-06-17); `[F]`=file count from the re-run. |
| §5.2.2, §1.4, Appendix A | "frontier **GPT-family** model" placeholders | name **gpt-5.4** (Azure OpenAI). |
| §4.4.1 | "the analyser-only-versus-hybrid contrast is also reported **across all three models**" | Remove (single-model study). |
| Appendix A, Level-2 Structural example | `Methods: 22 / Fields: 24 / LinesOfCode: 612` | Real God Class metrics, e.g. GC-01: `ATFD: 12 / WMC: 68 / TCC: 0.05`. Update the §C example prose ("22 methods and 24 fields across 612 lines") to ATFD/WMC/TCC. |
| §5.3.4 | prompt asks for "quality impact, problem, suggested repair, **and risks or assumptions**" | Drop "risks or assumptions" (v1.1.0 schema = explanation / quality_impact / remediation). Also retire/ignore `RunRecord.ParsedRisks`. |
| QA mapping table refs | referenced as Table 5.10 / 5.11 / B.10 inconsistently | Use one canonical number for the expected-attribute mapping. |

---

## Open questions & assumptions

- **LLM-only file scope** — **RESOLVED (2026-06-23):** `llm-only --target Corpus.sln` sweeps every corpus `.cs` (recall over the 30 instances + precision over clean/distractors); detections on non-instances are `is_spurious`. Implemented + unit-tested. Thesis §5.2.5 wording should note the LLM-only sweep covers all corpus files (precision measured over the clean/distractor set), not only the instance-spanning files.
- **Verified-repair scope across context** (H2b): apply/verify all 360 hybrid generations, or one run per (instance × level)? Assumed: all generations (objective metrics are computed on every generation per §5.2.5).
- F (file count) is filled after the re-run.

## Next steps

1. Implement Phase A (applier + build-gate + re-measure + RunRecord fields + stats). Decide LLM-only file scope first.
2. Phase B config + cross-model purge + `Architecture` tagging; point at `Corpus.sln`.
3. Phase C full re-run on gpt-5.4 (`--runs 3`); archive Ibis data.
4. Phases D–E (band agreement, R1 corpus review, re-rate the ~90-output contrast subset + IRR).
5. Apply the thesis punch-list and README fixes.
