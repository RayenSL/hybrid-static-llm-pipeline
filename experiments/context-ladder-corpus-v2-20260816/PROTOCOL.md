# Context-ladder corpus v2 experiment protocol

## Pre-registered design — frozen before any model call

- **Population:** all 36 detector-confirmed corpus v2.0 targets — 13 God Class, 13 Long Method,
  10 Obsolete API Usage.
- **Factor:** context level, four levels — Minimal, Structural, Relational, Full.
- **Repetitions:** 3 per target-level cell.
- **Volume:** 36 × 4 × 3 = **432 assignments**, one evaluated-model call each.
- **Architecture:** direct editing, single-shot. No applier. Visible generated tests **OFF**
  throughout — the supplement disabled them and adding the factor here would confound the dose.
- **Ladder:** `ladder-v2.0.0`, SHA-256
  `8c5bcdb50d61a13d439dbbcb9a7a5eb46270349d869bc254ab5b69c13a4dd86f`.
  Full = Relational + declaring source of every external type the target references, capped at
  8 files / 60,000 characters, ordered ordinally by relative path then declaring type name.
- **Prompt family:** `ladder-v1.0.0` (`ContextLadderPrompt`).
- **Starting state:** pristine corpus for every assignment, in an isolated working copy.
- **Retry policy:** none.

### Outcomes

**Primary:** verified repair — the edit builds **and** the triggering detector condition no longer
fires. Matched four-level comparison via Cochran's Q over target blocks; prespecified adjacent
contrast **Full − Relational**, since the cross-file rung is the one the mechanism predicts.
Remaining adjacent contrasts secondary, exact McNemar with Holm adjustment.

**Secondary:** ordinal repair ladder (`build_fails < builds_unresolved < resolved`); private
Layer 3 behavioural outcome; whole-solution Layer 1/2 quality change; prompt size, tokens and cost
per level; **cross-file truncation rate per level**.

### Pre-registered stratifications

1. **Successor availability (Obsolete API only).** Only **4 of 10** Obsolete API targets have an
   in-corpus successor (`SmsApiV2`, `LabelApiV2`, `MailApiV2`, `NotifyApiV2`). The other 6 carry
   deprecation notices explicitly stating no direct replacement (*"Removed; no replacement"*,
   *"Use IRateProvider"*, *"Use ICalendarWriter"*, *"Use IDocumentWriter"*), which §4.5.5 confirms
   is deliberate. The cross-file rung can only supply a successor where one exists, so the sharpest
   mechanism claim is testable on **n = 4**, not 10. **Verify this split against the fresh baseline
   in step 2 and record it before running.**
2. **Ceiling controls.** God Class and Long Method sit at 99.4% / 88.5% strict success under direct
   editing in the v2 factorial. They are pre-registered as ceiling controls: no movement is the
   expected result and is not a failed test. Report the MDE so the null is bounded, not open.

### Known threat to record now

A repair can resolve the detector **without migrating**. In the feasibility probe,
`CurrencyConverter` at Structural "resolved" by binding the same obsolete implementation through a
delegate so the detector's symbol resolution no longer saw a direct `[Obsolete]` reference. That is
detector evasion, and it is the §4.8 threshold-crossing threat. **Do not report detector resolution
alone as repair for Obsolete API.** Grade each resolved Obsolete API repair as
`migrated | evaded | ambiguous` from `parsed_suggested_fix` / the edited file, after sealing, and
report it beside the Layer 3 smoke result.
