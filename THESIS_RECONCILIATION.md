# Thesis ⇄ Implementation Reconciliation

**Source of truth:** the thesis PDF (`Z:\rayen\Combining_Static_Analysis_..._(14).pdf`, "Version of 23rd June 2026").
**Goal of this doc:** decisions taken + an executable plan to bring the implementation, data, and thesis text into agreement.

> Read first: the constructed corpus is **already built and faithful** to the thesis (separate repo `Z:\GitHub\hybrid-pipeline-corpus`). The detectors, context levels, and prompts (v1.1.0 hybrid, v1.2.0 LLM-only) in the pipeline **already match** the thesis. The real work is the verified-repair pipeline, re-pointing experiments at the corpus on a single model, and a batch of thesis-text fixes.

---

## Decisions log

| # | Topic | Decision |
|---|---|---|
| 1 | Output | Decisions + executable work plan (this doc). |
| 2 | Constructed corpus | Already built & authoritative. No rebuild. |
| 3 | Verified-repair pipeline | **Build it now** (thesis's primary objective metric). |
| 4 | Applier model | **claude-opus-4-8** (same family as the corpus generator; non-evaluated). |
| 5 | Frontier model | **gpt-5.4** via Azure OpenAI — single model for hybrid *and* LLM-only. |
| 6 | Multi-model | **Strictly single model.** Drop the 3-model H1a robustness check; purge cross-model code/analysis. |
| 7 | Dataset | **Discard the Ibis runs** (smoke tests). Corpus is the only dataset. |
| 8 | Band-verification | Run the **real HybridLens** analyser over the corpus and **report agreement** with `HybridLensMeasure`; keep both. |
| 9 | Thesis edits | **Punch-list only** (PDF; section-referenced edits below). |
| 10 | Corpus review | **Two-layer** (programmatic + R1). Drop reviewer_r2 from corpus verification. |
| 11 | Rubric IRR | **Keep R1 + R2** with Cohen's weighted κ on the IRR subset (§4.5 / B.8 unchanged). |

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
> `claude-opus-4-8` applier key in `appsettings.local.json`; and the `analyse_results.py` verified-repair
> stats (step 6). Note: `analyse` has no `--model` filter yet (ran all 3 configured models) — a Phase B item.

1. **Applier adapter + prompt.** Add a Claude applier (`claude-opus-4-8`) using the frozen **applier prompt v1.0.0** (thesis Appendix A.1). Contract: input = original file + finding + candidate repair; output = `{applicable, reason_if_not, edited_file}`. Strict-literal; no design decisions. Freeze each applier output as an artefact.
2. **Build gate.** Apply `edited_file` into a **working copy** of the corpus (never mutate the frozen corpus), then `dotnet build`. Build failure ⇒ scored as not-resolved.
3. **Re-measure.** On a green build, re-run the HybridLens detector on the applied file and recompute the triggering condition: GC composite (ATFD/WMC/TCC), LM (CC + LOC), OB (absence of the flagged `[Obsolete]` usage).
4. **Outcome.** Ordinal ladder `unapplicable < build_fails < builds_unresolved < resolved` (descriptive) + binary `verified_repair_success = applies ∧ builds ∧ metric_resolved` (inferential).
5. **RunRecord fields** (new): `applier_model`, `applier_prompt_version`, `applicable`, `unapplicable_reason`, `applied_source_ref`, `build_passed`, `remeasured_metrics`, `verified_repair_ladder`, `verified_repair_success`.
6. **Stats in `analyse_results.py`:** verified-repair % by architecture (Table 5.3) and by context level (Table 5.7) with Wilson CIs; **McNemar** paired hybrid vs LLM-only (H1b); **Cochran–Armitage** + **binomial GLMM** `verified_repair ~ ordered context + (1|instance)` (H2b); ladder distribution descriptive.
7. **Gaming guard:** human genuineness spot-check on a stratified 30% of metric-resolved repairs (R1, rubric anchors).
8. Apply/verify for **both** hybrid and LLM-only repairs; analyser-only = no repair (0 by construction).

### Phase B — Single-model + corpus wiring
9. Config: keep only **gpt-5.4** (Azure) as the evaluated model + **claude-opus-4-8** as the applier. Remove gpt-5.4-mini / DeepSeek / Llama / Mistral from the experiment config.
10. **Purge cross-model**: remove `loader.cross_model_agreement` and any cross-model outputs in `analyse_results.py`; delete the §4.4.1 "across all three models" robustness path.
11. Ensure `AnalysisPipeline` **populates `Architecture`** (`analyser_only` / `hybrid` / `llm_only`) — currently null in all data.
12. Point runs at `Z:\GitHub\hybrid-pipeline-corpus\corpus\Corpus.sln`.

### Phase C — Regenerate dataset
13. **Discard/retire Ibis data**: `analysis/experiments.json` and `src/runs-archive-pre-v1.1.0/` (already partly archived). Corpus only.
14. Run, all on gpt-5.4, `--runs 3`:
    - **Hybrid:** 30 × 4 context levels × 3 = **360** generations (prompt v1.1.0).
    - **Analyser-only:** 30 deterministic diagnostics (also serves the band re-confirmation in step 17).
    - **LLM-only:** prompt v1.2.0 over corpus files. **Open item:** scope = instance-spanning files (thesis §5.2.5 "3F") **vs** all corpus files incl. clean/distractors (needed to measure precision over distractors — README_HANDOFF says "pointed at `corpus/` ALONE"). Resolve before running (see Open questions).

### Phase D — Band agreement + verification
15. Run analyser-only (real HybridLens) over the corpus; **compare** measured metrics against `ground-truth/_measured/*` (HybridLensMeasure) for all 30; report agreement as a reliability point; update `measured_metrics` if any drift.
16. Complete **corpus R1 review** (`verification.reviewer_r1`) for all 30 instances; remove `reviewer_r2` from schema/records (two-layer).

### Phase E — Rating
17. Re-rate the **architecture-contrast subset only** (analyser-only, hybrid-Minimal, matched LLM-only at gpt-5.4 — ~90 outputs) under **rubric v1.0** (4 explanation + 4 repair dims, 7 hallucination categories, QA counts). Old `experiments.json` ratings (old `explanation_specificity`, single `hallucination_type`) are superseded.
18. R1 + R2 on the IRR subset; Cohen's weighted κ (`compare_raters.py`).

### Phase F — Docs
19. `README.md`: fix God Class config (ATFD/WMC/TCC, not Methods/Fields/LOC); default provider `claude`→`azure`/`gpt-5.4`; note context `Level` default.
20. Deliver the thesis punch-list below.

---

## Thesis text punch-list (PDF; section-referenced)

| Location | Current | Change to |
|---|---|---|
| §1.4, §4.5.1, §5.4.4 | "**eight**-category" hallucination taxonomy | "**seven**-category" (Table 5.9/5.10 list 7; code = 7). |
| §1.5 (contrib 2), §4.5.1 | "adding **three** further categories" | "retaining **3** HalluCode categories + adding **4**" (Table 5.9: 3 HalluCode-linked + 4 adapted = 7). |
| §4.3 | "borderline (**4 per type**) and clear-cut (**6 per type**)" | GC & LM = **5 clear-cut + 5 borderline** each; **OB = 10 clear-cut** (borderline N/A for a binary `[Obsolete]` marker), stratified by replacement availability (direct 4 / workaround 3 / removed 3). Net **20 clear-cut / 10 borderline**. |
| §4.3, §5.2.3 | "around **twelve** files without any seeded instances" | "**31** clean/distractor files." |
| §4.3, §5.2.3 | "**Four to six** independently compilable **solutions**" | "**one** solution (`Corpus.sln`) with **five** independently compilable .NET 8 **projects**, 11–14 files each (61 total)." |
| §4.7 | "**two-layer** verification protocol" | Keep **two-layer** (programmatic + R1). (Decision 10.) |
| §5.2.3 | "the **three-layer** protocol" | "the **two-layer** protocol." Also update the truth-record schema comment ("Three-layer protocol") + drop `reviewer_r2`. |
| §5.2.3, §5.2.4 placeholders | `[N]`, `[F]`, `[C]`, `[exact Claude model + version]` | `[N]`=5 projects; `[C]`=31; generator=`claude-opus-4-8`; prompt_template_version 1.0.0; frozen v1.0 (2026-06-17); `[F]`=file count from the re-run. |
| §5.2.2, §1.4, Appendix A | "frontier **GPT-family** model" placeholders | name **gpt-5.4** (Azure OpenAI). |
| §4.4.1 | "the analyser-only-versus-hybrid contrast is also reported **across all three models**" | Remove (single-model study). |
| Appendix A, Level-2 Structural example | `Methods: 22 / Fields: 24 / LinesOfCode: 612` | Real God Class metrics, e.g. GC-01: `ATFD: 12 / WMC: 68 / TCC: 0.05`. Update the §C example prose ("22 methods and 24 fields across 612 lines") to ATFD/WMC/TCC. |
| §5.3.4 | prompt asks for "quality impact, problem, suggested repair, **and risks or assumptions**" | Drop "risks or assumptions" (v1.1.0 schema = explanation / quality_impact / remediation). Also retire/ignore `RunRecord.ParsedRisks`. |
| QA mapping table refs | referenced as Table 5.10 / 5.11 / B.10 inconsistently | Use one canonical number for the expected-attribute mapping. |

---

## Open questions & assumptions

- **LLM-only file scope** (Phase C, step 14): instance-spanning files only (§5.2.5 "3F") vs **all** corpus files (needed for precision over distractors). Recommend: run over all corpus files; report recall over the 30 instances and precision over clean/distractors. Confirm + update §5.2.5.
- **Verified-repair scope across context** (H2b): apply/verify all 360 hybrid generations, or one run per (instance × level)? Assumed: all generations (objective metrics are computed on every generation per §5.2.5).
- **Spot-check rater** for the gaming guard = R1 (assumed).
- F (file count) is filled after the re-run.

## Next steps

1. Implement Phase A (applier + build-gate + re-measure + RunRecord fields + stats). Decide LLM-only file scope first.
2. Phase B config + cross-model purge + `Architecture` tagging; point at `Corpus.sln`.
3. Phase C full re-run on gpt-5.4 (`--runs 3`); archive Ibis data.
4. Phases D–E (band agreement, R1 corpus review, re-rate the ~90-output contrast subset + IRR).
5. Apply the thesis punch-list and README fixes.
