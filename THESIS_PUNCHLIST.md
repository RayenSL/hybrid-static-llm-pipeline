# Thesis punch-list — section-referenced edits

The thesis is the source of truth, but a few statements are internally inconsistent, stale relative
to the built corpus/implementation, or still placeholders. Below: **location → issue → find →
replace**, using values verified from the implementation and the frozen corpus (`hybrid-pipeline-corpus`
v1.0, manifest `2026-06-17`). Apply in Overleaf/Word. Companion to [THESIS_RECONCILIATION.md](THESIS_RECONCILIATION.md).

Verified reference values used throughout:
- Detector thresholds: **ATFD > 4, WMC ≥ 47, TCC < 1/3, CC > 10, LOC > 50** (`appsettings.json` = corpus `analyser-config.json`).
- Corpus: **5 .NET 8 projects in one `Corpus.sln`, 61 files**, **30 seeded** (10 GodClass / 10 LongMethod / 10 ObsoleteApiUsage), **31 clean/distractor** files.
- Strata: **20 clear-cut / 10 borderline** — GodClass 5+5, LongMethod 5+5, ObsoleteApiUsage 10 clear-cut + 0 borderline (a binary `[Obsolete]` marker has no borderline band; OB is stratified by replacement availability instead: **direct 4 / workaround 3 / removed 3**).
- Generator (non-evaluated): **claude-opus-4-8**; evaluated frontier model: **gpt-5.4** (Azure OpenAI); applier (non-evaluated): **DeepSeek-V4-Pro** (Azure).
- Corpus frozen **v1.0**, MIT, repo `github.com/aceve/hybridlens-corpus`.

---

## A. Hallucination taxonomy: "eight" → "seven" (and the additions count)

The prose says eight categories with three additions, but Table 5.9, Table 5.10 and the
implementation (`score_runs.py`) all enumerate **seven**: factual fabrication, context inconsistency,
intent mismatch, incomplete suggestion, irrelevant suggestion, risky repair, over-generalisation.
Per Table 5.9's literature column that is **3 retained from HalluCode + 4 adapted = 7**.

1. **§1.4 (Approach)** — find "an eight-category hallucination taxonomy" → "a seven-category hallucination taxonomy".
2. **§1.5 (Contribution 2)** — find "retaining the categories applicable to the explanation-and-repair setting and adding three further categories" → "retaining three HalluCode categories applicable to the explanation-and-repair setting and adding four further categories".
3. **§4.5.1 (Hallucination categorisation)** — find "An eight-category taxonomy derived from Liu et al. [25] with three thesis-specific additions based on pilot data" → "A seven-category taxonomy derived from Liu et al. [25] — three HalluCode categories retained and four thesis-specific additions based on pilot data".
4. **§5.4.4** — find "The eight-category taxonomy" → "The seven-category taxonomy".

---

## B. Corpus shape, strata, counts, placeholders

5. **§4.3 (Corpus shape)** — find "Four to six independently compilable solutions (five to fifteen files apiece)" → "Five independently compilable .NET 8 projects in a single solution (eleven to fourteen files apiece, 61 files total)".
6. **§4.3 (Seeded instances and strata)** — find "Instances within each kind were divided into borderline (4 per type, values just fulfilling the criteria) and clear-cut (6 per type, values easily past threshold)." → "God Class and Long Method instances are each split into 5 clear-cut and 5 borderline (values just fulfilling the criteria). Obsolete API Usage has no borderline band — a `[Obsolete]` marker is binary present/absent — so its ten instances are all clear-cut and are instead stratified by replacement availability (direct 4, workaround 3, removed 3). Net: 20 clear-cut, 10 borderline."
7. **§4.3 (Controls and distractors)** — find "There are around twelve files without any seeded instances" → "There are 31 files without any seeded instances".
8. **§5.2.3 (Dataset)** placeholders — set: `[N]` = **5 projects**; total files `[F]` = **61**; `[C]` control/distractor files = **31**; `[exact Claude model + version]` = **claude-opus-4-8**; corpus tag **v1.0**, frozen **2026-06-17**, **MIT**, repo `github.com/aceve/hybridlens-corpus`. Also reword "independently compilable .NET solutions" → "independently compilable .NET projects (one solution)".
9. **§5.2.3 / §4.7 — verification layers.** Decision: corpus verification is **two-layer** (programmatic + a single human reviewer R1; the second corpus reviewer R2 was dropped). In **§5.2.3** find "the three-layer protocol" → "the two-layer protocol". Confirm **§4.7** stays "two-layer verification protocol" and describes only R1 (no R2) for the corpus. (The rubric IRR keeps R1+R2 — that is a *separate* second rater, §4.5/B.8, unchanged.)
10. **§5.2.4 (Ground Truth)** — set generator model/version = **claude-opus-4-8**; `prompt_template_version` = **1.0.0**. Fix the broken "Table ??" reference for the expected ISO/IEC 25010 mapping to **Table 5.11** (and **Table B.10** in the appendix).
11. **§5.2.5 (Generations)** — "30 × 4 × 3 = 360 hybrid generations" is correct. Clarify **F**: the agentic "3F" uses *F = number of distinct files spanned by the 30 instances* (not the 61-file corpus total). State the resolved F once the run is done. (Default run scope is instance-spanning files only; `--sweep-corpus` widens to all 61 for fuller precision — note whichever was used.)

---

## C. Detection rules (Table 5.1)

12. **Table 5.1** — fill the bracketed thresholds with the configured values: God Class **ATFD > 4**, **WMC ≥ 47**, **TCC < 1/3**; Long Method **cyclomatic complexity > 10**, **lines of code > 50** (secondary); Obsolete API **`[Obsolete]` present (binary)**. (§5.1.2 says "the configured numeric values … are given in Table 5.1".)

---

## D. Prompt appendix (Appendix A) — stale God Class metrics

The Level-2/Full examples and the expected-response prose show count-based God Class metrics
(`Methods / Fields / LinesOfCode`), but the detector (and §4.2.1/§5.1.2) compute ATFD/WMC/TCC.

13. **Appendix A, Level 2 (Structural) & Level 4 (Full) — Metrics block** — find
    ```
    Methods: 22
    Fields: 24
    LinesOfCode: 612
    ```
    → use a real corpus example (GC-01, `Ordering.OrderProcessor`):
    ```
    ATFD: 12
    WMC: 68
    TCC: 0.0455
    ```
14. **Appendix A, §C (Expected response) explanation text** — find "With 22 methods and 24 fields across 612 lines of code, it concentrates …" → "With ATFD 12 (foreign-data accesses), WMC 68 (aggregate method complexity) and TCC 0.05 (very low cohesion), it concentrates …".

---

## E. Single frontier model

15. **§5.2.2 / §1.4 / Appendix A** — replace the "frontier GPT-family model" / "[exact GPT model + version]" placeholders with **gpt-5.4 (Azure OpenAI)**.
16. **§4.4.1 (Architecture comparison)** — **remove** the robustness sentence "As a robustness check, the analyser-only-versus-hybrid contrast is also reported across all three models." (Strictly single model; the cross-model analysis was removed in the implementation.)
17. **§4.6** — confirm the line stating "the former Cochran's Q comparison of alignment rate across models is removed" remains, and that no other between-model test survives in the text.
18. **§5.2.3 / §4.3** — applier = **DeepSeek-V4-Pro** (Azure; non-evaluated). It is a different family from **both** the evaluated gpt-5.4 and the corpus generator (claude-opus-4-8), so **split the thesis wording** that currently ties the applier to "the same family that produced the corpus": generator = claude-opus-4-8, applier = DeepSeek-V4-Pro. The anti-contamination safeguard still holds — the evaluated gpt-5.4 never applies its own repairs.

---

## F. Agentic arm (Appendix E v2.0.0) — leftover "LLM-only" labels

The third arm is the **agentic** arm (§4.4.1; Appendix E is titled "agentic prompt and loop contract
(v2.0.0)"), but several labels inside Appendix E still read "(LLM-only)" from the single-shot draft.
The implementation now matches the agentic loop (CLI `agentic`, prompt v2.0.0, architecture tag
`agentic`, compiler-in-the-loop, final solution scored in-runner).

19. **Appendix E subsection labels** — find "E.1 System prompt **(LLM-only)**", "E.2 User prompt **(LLM-only)**", "E.3 Expected response **(LLM-only)**" → replace "(LLM-only)" with "(agentic)" in all three.
20. **Appendix E running header** — the page header reads "**LLM prompt (v1.1.0)**" on the agentic-appendix pages; it should reference the agentic prompt **v2.0.0**.
21. **§4.5.1 / Appendix A.1 applier wording** — the thesis says "a non-evaluated **Claude-family** applier"; the implementation default applier is **DeepSeek-V4-Pro** (Azure). Either name DeepSeek-V4-Pro or generalise to "a non-evaluated applier from a different family than the evaluated gpt-5.4" (see also item 18). Note the agentic arm needs **no** applier — its final edited solution is scored directly (§4.7.1), which the thesis already states.

## G. Misc

22. **§5.3.4 (Prompt Construction Validation)** — find "structured chunks covering the quality impact, problem, suggested repair, and risks or assumptions" → "structured fields covering the explanation, the quality impact, and the suggested repair" (the v1.1.0 schema has no separate risks/assumptions field).
23. **Broken cross-references** — the draft has many unresolved `??` (e.g. "§??", "Table ??", "Appendix ??"). Resolve them in LaTeX; the high-value ones: the architecture-comparison section (referenced as "§??" / "S5.1.1") should point to **§4.4.1**; the rubric appendix references should point to **Appendix B**; the expected-mapping table to **Table 5.11 / B.10**.

---

## H. Corpus-repo follow-ups (not the thesis — `hybrid-pipeline-corpus`)

These mirror the two-layer decision (B.9) and keep the published artefacts consistent:
24. `schema/truth-record.schema.json` — the `verification` block comment says "Three-layer protocol"; change to two-layer and **drop the `reviewer_r2` property** (and `disagreement_resolution` if it only served R1/R2 reconciliation).
25. `ground-truth/records/*.json` — populate `verification.reviewer_r1` for all 30 (single reviewer); remove `reviewer_r2`.
26. `RUNBOOK.md` / `CLAUDE.md` / `tools/Measure/Measure.csproj` — references to "Table 5.10" for the ISO mapping should match the thesis's table number (5.11 / B.10); wording "three-layer" → "two-layer".
27. `manifest.json` `repository` is `github.com/aceve/hybridlens-corpus` — confirm that's the intended public URL before release.
28. **§4.5.1 "same code" claim now holds.** The corpus `measured_metrics` were re-derived from the real HybridLens detector (the separate `HybridLensMeasure` tool diverged on GodClass ATFD/WMC — HL counts more foreign accesses and sums slightly less complexity — and one LongMethod CC; detection was unaffected). So "the same metric implementation that certifies seeded instances is the same code that generates the analyser flags" is now literally true. Optionally note in §4.7/§5.2.3 that `HybridLensMeasure` was a generation-time band-control helper, superseded by the HybridLens detector for the published measured values.
