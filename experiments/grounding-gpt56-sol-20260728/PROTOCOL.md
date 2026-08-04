# GPT-5.6 Sol four-level grounding experiment protocol

## Status and scope

This is a separately frozen supplementary experiment added after completion of the
2 x 2 x 2 characterization-test factorial. It does not overwrite, extend denominators
within, or retroactively alter that confirmatory experiment. No four-level grounding
outcome was inspected before this protocol and assignment schedule were frozen.

## Design

- Evaluated model: `gpt-5.6-sol` through the configured Azure deployment.
- Non-evaluated strict-literal applier: `DeepSeek-V4-Pro`, held constant.
- Subjects: all 30 detector-confirmed corpus targets: 10 God Class, 10 Long Method,
  and 10 Obsolete API Usage.
- Factor: Minimal, Structural, Relational, Full context.
- Repetitions: one per target-context cell.
- Volume: 30 x 4 = 120 evaluated-model calls, plus at most 120 applier calls.
- Architecture: original Hybrid explanation/remediation pipeline followed by the
  frozen strict-literal applier, a clean build, and detector remeasurement.
- Visible generated tests: disabled in every condition.
- Starting state: pristine corpus for every applied repair.
- Randomization: target blocks randomized; four context levels randomized within
  every target block using seed 20260728.
- Retry policy: no model-call retry. API/parse/application/build failures remain outcomes.

## Context levels

- Minimal: anti-pattern label and detector-extracted code fragment.
- Structural: Minimal plus symbol, file/line location, severity, metrics, and thresholds.
- Relational: Structural plus member summary and surrounding source window.
- Full: Relational plus factual project metadata. Because every seeded target is in a
  unique file, co-located findings are absent by construction. Full metadata is frozen
  from the corpus truth manifest: Framework=.NET 8, Project=<project>, Domain=<domain>.

## Outcomes

Primary outcome: verified repair success, defined identically across anti-patterns as
strict-literal application succeeded, the resulting solution built, and the triggering
detector condition no longer fired.

Secondary outcomes:

- ordinal repair ladder: unapplicable < build fails < builds unresolved < resolved;
- result stratified by anti-pattern;
- private Layer 3 outcome, reported separately because God Class/Long Method use
  behavioral equivalence while Obsolete API Usage uses a smoke oracle;
- lexical ISO/IEC 25010 mention/alignment;
- whole-solution Layer 1/Layer 2 quality change on materialized final states;
- evaluated-model and applier input/output tokens, duration, and nominal Sol cost;
- context prompt size.

## Statistical analysis

- Global matched four-level comparison: Cochran's Q on the 30 target blocks.
- Prespecified primary pairwise contrast: Structural versus Minimal.
- Secondary adjacent contrasts: Relational versus Structural and Full versus Relational.
- Pairwise binary tests: exact McNemar with Holm adjustment over the three adjacent contrasts.
- Report paired risk differences with target-level confidence intervals.
- Report overall and per-anti-pattern counts; per-pattern results are descriptive with n=10.
- One repetition prevents estimation of within-cell stochastic variance and is reported as
  a resource-constrained limitation.

## Integrity and reporting

Every assignment receives its own append-only trace. A campaign ledger records completion,
trace hash, call counts, and tokens. Completed assignments are never repeated on resume.
All materialized final sources are evaluated privately only after the repair campaign is
sealed, then reconstructed as complete viewable corpus archives. Results are added to the
final Chapter 5.4 package as a separate four-level grounding result, while the completed
confirmatory factorial remains unchanged.
